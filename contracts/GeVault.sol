// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;

import "./openzeppelin-solidity/contracts/access/Ownable.sol";
import "./openzeppelin-solidity/contracts/token/ERC20/ERC20.sol";
import "./openzeppelin-solidity/contracts/token/ERC20/utils/SafeERC20.sol";
import "./openzeppelin-solidity/contracts/security/ReentrancyGuard.sol";
import "../interfaces/IAaveLendingPoolV2.sol";
import "../interfaces/IUniswapV3Pool.sol";
import "../interfaces/IWETH.sol";
import "../interfaces/IPriceOracle.sol";
import "./RoeRouter.sol";
import "./TokenisableRange.sol";

/**
GeVault is a reblancing vault that holds TokenisableRanges tickers
Functionalities:
- Hold a list of tickers for a single pair, evenly spaced
- Hold balances of those tickers, deposited in the ROE LP
- Deposit one underlying asset split evenly into 2 or more consecutive ticks above/below the current price
- Withdraw one underlying asset, taken out evenly from 2 or more consecutive ticks
- Calculate the current balance of assets

Design:
 
 */
contract GeVault is ERC20, Ownable, ReentrancyGuard {
  using SafeERC20 for ERC20;
  
  event Deposit(address indexed sender, address indexed token, uint amount, uint liquidity);
  event Withdraw(address indexed sender, address indexed token, uint amount, uint liquidity);
  event PushTick(address indexed ticker);
  event ShiftTick(address indexed ticker);
  event ModifyTick(address indexed ticker, uint index);
  event Rebalance(uint tickIndex);
  event SetEnabled(bool isEnabled);
  event SetTreasury(address treasury);
  event SetFee(uint baseFeeX4);
  event SetTvlCap(uint tvlCap);
  event SetLiquidityPerTick(uint8 liquidityPerTick);
  event SetFullRangeShare(uint8 fullRangeShare);
  event DepositedFees(address token, uint amount, uint value);

  /// @notice Ticks properly ordered in ascending price order
  TokenisableRange[] public ticks;
  /// @notice Full range position
  TokenisableRange public immutable fullRange;

  /// immutable keyword removed for coverage testing bug in brownie
  /// @notice Pair tokens
  ERC20 public immutable token0;
  ERC20 public immutable token1;
  bool public isEnabled = true;
  bool private baseTokenIsToken0;
  /// @notice Pool base fee 
  uint24 public baseFeeX4 = 20;
  // Split underlying liquidity on X ticks below and X above current price. More volatile assets would benefit from being spread out
  uint8 public liquidityPerTick = 3;
  uint8 public fullRangeShare = 20;
  /// @notice Max vault TVL with 8 decimals
  uint96 public tvlCap = 1e12;
  address public treasury;
  
  IUniswapV3Pool public uniswapPool;
  ILendingPool public lendingPool;
  IPriceOracle public oracle;
  IWETH private WETH;
  
  /// CONSTANTS 
  uint256 internal constant Q96 = 0x1000000000000000000000000;
  uint internal constant UINT256MAX = type(uint256).max;
  int24 internal constant MIN_TICK = -887272;
  int24 internal constant MAX_TICK = -MIN_TICK;

  constructor(
    address _treasury, 
    address roeRouter, 
    address _uniswapPool, 
    uint poolId, 
    string memory name, 
    string memory symbol,
    address weth,
    bool _baseTokenIsToken0,
    address fullRange_
  ) 
    ERC20(name, symbol)
  {
    require(_treasury != address(0x0), "GEV: Invalid Treasury");
    require(_uniswapPool != address(0x0), "GEV: Invalid Pool");
    require(weth != address(0x0), "GEV: Invalid WETH");

    (address lpap, address _token0, address _token1,, ) = RoeRouter(roeRouter).pools(poolId);
    token0 = ERC20(_token0);
    token1 = ERC20(_token1);
    
    TokenisableRange t = TokenisableRange(fullRange_);
    (ERC20 t0,) = t.TOKEN0();
    (ERC20 t1,) = t.TOKEN1();
    require(t0 == token0 && t1 == token1, "GEV: Invalid TR");
    // check that the full range makes sense: MIN_TICK=-887272, MAX_TICK=-MIN_TICK, with a granularity based on fee tier
    require(t.lowerTick() < -887200 && t.upperTick() > 887200, "GEV: Invalid Full Range");
    fullRange = t;
    
    lendingPool = ILendingPool(ILendingPoolAddressesProvider(lpap).getLendingPool());
    oracle = IPriceOracle(ILendingPoolAddressesProvider(lpap).getPriceOracle());
    treasury = _treasury;
    baseTokenIsToken0 = _baseTokenIsToken0;
    uniswapPool = IUniswapV3Pool(_uniswapPool);
    WETH = IWETH(weth);
  }
  
  
  //////// ADMIN
  
  
  /// @notice Set pool status
  /// @param _isEnabled Pool status
  function setEnabled(bool _isEnabled) public onlyOwner { 
    isEnabled = _isEnabled; 
    emit SetEnabled(_isEnabled);
  }
  
  /// @notice Set treasury address
  /// @param newTreasury New address
  function setTreasury(address newTreasury) public onlyOwner { 
    treasury = newTreasury; 
    emit SetTreasury(newTreasury);
  }  
  
  
  /// @notice Set liquidityPerTick (how much of assets each tick gets)
  /// @param _liquidityPerTick proportion of liquidity in each nearby tick
  function setLiquidityPerTick(uint8 _liquidityPerTick) public onlyOwner { 
    require(_liquidityPerTick > 1, "GEV: Invalid LPT");
    liquidityPerTick = _liquidityPerTick; 
    emit SetLiquidityPerTick(_liquidityPerTick);
  }
  
  
  /// @notice Set fullRangeShare (how much of assets go into the full range)
  /// @param _fullRangeShare proportion of liquidity going to full range
  /// @dev Since full range is balanced between both assets, the share is taken according to lowest available token
  /// That share is therefore strictly lower that the TVL total
  function setFullRangeShare(uint8 _fullRangeShare) public onlyOwner { 
    require(_fullRangeShare < 100, "GEV: Invalid FRS");
    fullRangeShare = _fullRangeShare; 
    emit SetLiquidityPerTick(_fullRangeShare);
  }


  /// @notice Add a new ticker to the list
  /// @param tr Tick address
  function pushTick(address tr) public onlyOwner {
    TokenisableRange t = TokenisableRange(tr);
    (ERC20 t0,) = t.TOKEN0();
    (ERC20 t1,) = t.TOKEN1();
    require(t0 == token0 && t1 == token1, "GEV: Invalid TR");
    if (ticks.length == 0) ticks.push(t);
    else {
      // Check that tick is properly ordered
      if (baseTokenIsToken0) 
        require( t.lowerTick() > ticks[ticks.length-1].upperTick(), "GEV: Push Tick Overlap");
      else 
        require( t.upperTick() < ticks[ticks.length-1].lowerTick(), "GEV: Push Tick Overlap");
      
      ticks.push(TokenisableRange(tr));
    }
    emit PushTick(tr);
  }  


  /// @notice Add a new ticker to the list
  /// @param tr Tick address
  function shiftTick(address tr) public onlyOwner {
    TokenisableRange t = TokenisableRange(tr);
    (ERC20 t0,) = t.TOKEN0();
    (ERC20 t1,) = t.TOKEN1();
    require(t0 == token0 && t1 == token1, "GEV: Invalid TR");
    if (ticks.length == 0) ticks.push(t);
    else {
      // Check that tick is properly ordered
      if (!baseTokenIsToken0) 
        require( t.lowerTick() > ticks[0].upperTick(), "GEV: Shift Tick Overlap");
      else 
        require( t.upperTick() < ticks[0].lowerTick(), "GEV: Shift Tick Overlap");
      
      // extend array by pushing last elt
      ticks.push(ticks[ticks.length-1]);
      // shift each element
      if (ticks.length > 2){
        for (uint k = 0; k < ticks.length - 2; k++) 
          ticks[ticks.length - 2 - k] = ticks[ticks.length - 3 - k];
        }
      // add new tick in first place
      ticks[0] = t;
    }
    emit ShiftTick(tr);
  }


  /// @notice Modify ticker
  /// @param tr New tick address
  /// @param index Tick to modify
  function modifyTick(address tr, uint index) public onlyOwner {
    (ERC20 t0,) = TokenisableRange(tr).TOKEN0();
    (ERC20 t1,) = TokenisableRange(tr).TOKEN1();
    require(t0 == token0 && t1 == token1, "GEV: Invalid TR");
    removeFromAllRanges();
    ticks[index] = TokenisableRange(tr);
    if (isEnabled) deployAssets();
    emit ModifyTick(tr, index);
  }
  
  /// @notice Ticks length getter
  /// @return len Ticks length
  function getTickLength() public view returns(uint len){
    len = ticks.length;
  }
  
  /// @notice Set the base fee
  /// @param newBaseFeeX4 New base fee in E4
  function setBaseFee(uint24 newBaseFeeX4) public onlyOwner {
    require(newBaseFeeX4 < 1e4, "GEV: Invalid Base Fee");
    baseFeeX4 = newBaseFeeX4;
    emit SetFee(newBaseFeeX4);
  }
  
  /// @notice Set the TVL cap
  /// @param newTvlCap New TVL cap
  function setTvlCap(uint96 newTvlCap) public onlyOwner {
    tvlCap = newTvlCap;
    emit SetTvlCap(newTvlCap);
  }
  
  
  //////// PUBLIC FUNCTIONS
  
    
  /// @notice Rebalance tickers
  /// @dev Provide the list of tickers from 
  function rebalance() public {
    require(poolMatchesOracle(), "GEV: Oracle Error");
    removeFromAllRanges();
    if (isEnabled) deployAssets();
  }
  

  /// @notice Withdraw assets from the ticker
  /// @param liquidity Amount of GEV tokens to redeem; if 0, redeem all
  /// @param token Address of the token redeemed for
  /// @return amount Total token returned
  /// @dev For simplicity+efficieny, withdrawal is like a rebalancing, but a subset of the tokens are sent back to the user before redeploying
  function withdraw(uint liquidity, address token) public nonReentrant returns (uint amount) {
    require(poolMatchesOracle(), "GEV: Oracle Error");
    if (liquidity == 0) liquidity = balanceOf(msg.sender);
    require(liquidity <= balanceOf(msg.sender), "GEV: Insufficient Balance");
    require(liquidity > 0, "GEV: Withdraw Zero");
    
    uint vaultValueX8 = getTVL();
    uint valueX8 = vaultValueX8 * liquidity / totalSupply();
    amount = valueX8 * 10**ERC20(token).decimals() / oracle.getAssetPrice(token);
    uint fee = amount * getAdjustedBaseFee(token == address(token1)) / 1e4;
    
    _burn(msg.sender, liquidity);
    removeFromAllRanges();
    ERC20(token).safeTransfer(treasury, fee);
    uint bal = amount - fee;

    if (token == address(WETH)){
      WETH.withdraw(bal);
      (bool success, ) = payable(msg.sender).call{value: bal}("");
      require(success, "GEV: Error sending ETH");
    }
    else {
      ERC20(token).safeTransfer(msg.sender, bal);
    }
    
    // if pool enabled, deploy assets in ticks, otherwise just let assets sit here until totally withdrawn
    if (isEnabled) deployAssets();
    emit Withdraw(msg.sender, token, amount, liquidity);
  }

  /// @notice deposit tokens in the pool as fee (donation, do not create liquidity)
  /// @param token Token address
  /// @param amount Amount of token deposited
  function depositFee(address token, uint amount) public nonReentrant {
    require(amount > 0, "GEV: Deposit Zero");
    require(isEnabled, "GEV: Pool Disabled");
    require(token == address(token0) || token == address(token1), "GEV: Invalid Token");
    ERC20(token).safeTransferFrom(msg.sender, address(this), amount);
    uint valueFee = oracle.getAssetPrice(token) * amount;
    emit DepositedFees(token, amount, valueFee);
  }


  /// @notice deposit tokens in the pool, convert to WETH if necessary
  /// @param token Token address
  /// @param amount Amount of token deposited
  function deposit(address token, uint amount) public payable nonReentrant returns (uint liquidity) 
  {
    require(amount > 0 || msg.value > 0, "GEV: Deposit Zero");
    require(isEnabled, "GEV: Pool Disabled");
    require(token == address(token0) || token == address(token1), "GEV: Invalid Token");
    require(poolMatchesOracle(), "GEV: Oracle Error");
    
    // first remove all liquidity so as to force pending fees transfer
    removeFromAllRanges();
    
    uint vaultValueX8 = getTVL();   
    uint adjBaseFee = getAdjustedBaseFee(token == address(token0));
    // Wrap if necessary and deposit here
    if (msg.value > 0){
      require(token == address(WETH), "GEV: Invalid Weth");
      // wraps ETH by sending to the wrapper that sends back WETH
      WETH.deposit{value: msg.value}();
      amount = msg.value;
    }
    else { 
      ERC20(token).safeTransferFrom(msg.sender, address(this), amount);
    }
    
    // Send deposit fee to treasury
    uint fee = amount * adjBaseFee / 1e4;
    ERC20(token).safeTransfer(treasury, fee);
    uint valueX8 = oracle.getAssetPrice(token) * (amount - fee) / 10**ERC20(token).decimals();

    require(tvlCap > valueX8 + vaultValueX8, "GEV: Max Cap Reached");

    uint tSupply = totalSupply();
    // initial liquidity at 1e18 token ~ $1
    if (tSupply == 0 || vaultValueX8 == 0)
      liquidity = valueX8 * 1e10;
    else {
      liquidity = tSupply * valueX8 / vaultValueX8;
    }
    
    deployAssets();
    require(liquidity > 0, "GEV: No Liquidity Added");
    _mint(msg.sender, liquidity);    
    emit Deposit(msg.sender, token, amount, liquidity);
  }
  
  
  /// @notice Get value of 1e18 GEV tokens
  /// @return priceX8 price of 1e18 tokens with 8 decimals
  function latestAnswer() external view returns (uint256 priceX8) {
    uint supply = totalSupply();
    if (supply == 0) return 0;
    uint vaultValue = getTVL();
    priceX8 = vaultValue * 1e18 / supply;
  }


  //////// INTERNAL FUNCTIONS
  
  /// @notice Remove assets from all the underlying ticks
  function removeFromAllRanges() internal {
    uint fullRangeBal = fullRange.balanceOf(address(this));
    if (fullRangeBal > 0) fullRange.withdraw(fullRangeBal, 0, 0);
    for (uint k = 0; k < ticks.length; k++){
      removeFromTick(k);
    }    
  }
  
  
  /// @notice Remove from tick
  function removeFromTick(uint index) internal {
    TokenisableRange tr = ticks[index];
    address aTokenAddress = lendingPool.getReserveData(address(tr)).aTokenAddress;
    uint aBal = ERC20(aTokenAddress).balanceOf(address(this));
    uint sBal = tr.balanceOf(aTokenAddress);

    // if there are less tokens available than the balance (because of outstanding debt), withdraw what's available
    if (aBal > sBal) aBal = sBal;
    if (aBal > 0){
      lendingPool.withdraw(address(tr), aBal, address(this));
      tr.withdraw(aBal, 0, 0);
    }
  }
  
  
  /// @notice 
  function deployAssets() internal { 
    if (ticks.length == 0) return;
    uint newTickIndex = getActiveTickIndex();
    uint availToken0 = token0.balanceOf(address(this));
    uint availToken1 = token1.balanceOf(address(this));
    
    // deposit a part of the assets in the full range. No slippage control in TR since we already checked here for sandwich
    if (availToken0 > 0 && availToken1 > 0) {
      uint amount0 = availToken0 * fullRangeShare / 100;
      uint amount1 = availToken1 * fullRangeShare / 100;
      checkSetApprove(address(token0), address(fullRange), amount0);
      checkSetApprove(address(token1), address(fullRange), amount1);
      fullRange.depositExactly(amount0, amount1, 0, 0);
    }
    availToken0 = token0.balanceOf(address(this));
    availToken1 = token1.balanceOf(address(this));

    // if base token is token0, ticks above only contain base token = token0 and ticks below only hold quote token = token1
    if (newTickIndex > 1) 
      depositAndStash(
        ticks[newTickIndex-2], 
        baseTokenIsToken0 ? 0 : availToken0 / liquidityPerTick,
        baseTokenIsToken0 ? availToken1 / liquidityPerTick : 0
      );
    if (newTickIndex > 0) 
      depositAndStash(
        ticks[newTickIndex-1], 
        baseTokenIsToken0 ? 0 : availToken0 / liquidityPerTick,
        baseTokenIsToken0 ? availToken1 / liquidityPerTick : 0
      );
    if (newTickIndex < ticks.length) 
      depositAndStash(
        ticks[newTickIndex], 
        baseTokenIsToken0 ? availToken0 / liquidityPerTick : 0,
        baseTokenIsToken0 ? 0 : availToken1 / liquidityPerTick
      );
    if (newTickIndex+1 < ticks.length) 
      depositAndStash(
        ticks[newTickIndex+1], 
        baseTokenIsToken0 ? availToken0 / liquidityPerTick : 0,
        baseTokenIsToken0 ? 0 : availToken1 / liquidityPerTick
      );

    emit Rebalance(newTickIndex);
  }
  
  
  /// @notice Checks that the pool price isn't manipulated
  function poolMatchesOracle() public view returns (bool matches){
    (uint160 sqrtPriceX96,,,,,,) = uniswapPool.slot0();
    
    uint token0Decimals = token0.decimals();
    uint token1Decimals = token1.decimals();
    uint priceX8;

    // Based on https://github.com/rysk-finance/dynamic-hedging/blob/HOTFIX-14-08-23/packages/contracts/contracts/vendor/uniswap/RangeOrderUtils.sol
    uint256 sqrtPrice = uint256(sqrtPriceX96);
    if (sqrtPrice > Q96) {
        uint256 sqrtP = FullMath.mulDiv(sqrtPrice, 10 ** token0Decimals, Q96);
        priceX8 = FullMath.mulDiv(sqrtP, sqrtP, 10 ** token0Decimals);
    } else {
        uint256 numerator1 = FullMath.mulDiv(sqrtPrice, sqrtPrice, 1);
        uint256 numerator2 = 10 ** token0Decimals;
        priceX8 = FullMath.mulDiv(numerator1, numerator2, 1 << 192);
    }
    
    priceX8 = priceX8 * 10**8 / 10**token1Decimals;
    uint oraclePrice = 1e8 * oracle.getAssetPrice(address(token0)) / oracle.getAssetPrice(address(token1));
    if (oraclePrice < priceX8 * 101 / 100 && oraclePrice > priceX8 * 99 / 100) matches = true;
  }


  /// @notice Helper that checks current allowance and approves if necessary
  /// @param token Target token
  /// @param spender Spender
  /// @param amount Amount below which we need to approve the token spending
  function checkSetApprove(address token, address spender, uint amount) private {
    uint currentAllowance = ERC20(token).allowance(address(this), spender);
    if (currentAllowance < amount) ERC20(token).safeIncreaseAllowance(spender, UINT256MAX - currentAllowance);
  }
  
  
  /// @notice Calculate the vault total ticks value
  /// @return valueX8 Total value of the vault with 8 decimals
  function getTVL() public view returns (uint valueX8){
    (,, valueX8) = getReserves();
  }
  
  
  /// @notice Get vault underlying assets
  function getReserves() public view returns (uint amount0, uint amount1, uint valueX8){
    // full range amounts
    (amount0, amount1) = fullRange.getTokenAmounts(fullRange.balanceOf(address(this)));
    // undeposited tokens
    amount0 += token0.balanceOf(address(this));
    amount1 += token1.balanceOf(address(this));
    // ticks amounts
    for (uint k = 0; k < ticks.length; k++){
      TokenisableRange t = ticks[k];
      address aTick = lendingPool.getReserveData(address(t)).aTokenAddress;
      uint bal = ERC20(aTick).balanceOf(address(this));
      (uint amt0, uint amt1) = t.getTokenAmounts(bal);
      amount0 += amt0;
      amount1 += amt1;
    }
    valueX8 = amount0 * oracle.getAssetPrice(address(token0)) / 10**token0.decimals() 
            + amount1 * oracle.getAssetPrice(address(token1)) / 10**token1.decimals();
  }
  
  /// @notice Get balance of tick deposited in GE
  /// @param index Tick index
  /// @return liquidity Amount of Ticker
  function getTickBalance(uint index) public view returns (uint liquidity) {
    TokenisableRange t = ticks[index];
    address aTokenAddress = lendingPool.getReserveData(address(t)).aTokenAddress;
    liquidity = ERC20(aTokenAddress).balanceOf(address(this));
  }
  
  
  /// @notice Deposit assets in a ticker, and the ticker in lending pool
  /// @param t Tik address
  /// @return liquidity The amount of ticker liquidity added
  function depositAndStash(TokenisableRange t, uint amount0, uint amount1) internal returns (uint liquidity){
    if (amount0 == 0 && amount1 == 0) return 0;
    checkSetApprove(address(token0), address(t), amount0);
    checkSetApprove(address(token1), address(t), amount1);
    try t.deposit(amount0, amount1) returns (uint lpAmt){
      liquidity = lpAmt;
    }
    catch {
      return 0;
    }
    
    uint bal = t.balanceOf(address(this));
    if (bal > 0){
      checkSetApprove(address(t), address(lendingPool), bal);
      lendingPool.deposit(address(t), bal, address(this), 0);
    }
  }

  
  /// @notice Return first valid tick
  function getActiveTickIndex() public view returns (uint activeTickIndex) {
    // loop on all ticks, if underlying is only base token then we are above, and tickIndex is 2 below
    for (uint tickIndex = 0; tickIndex < ticks.length; tickIndex++){
      (uint amt0, uint amt1) = ticks[tickIndex].getTokenAmountsExcludingFees(1e18);
      // found a tick that's above price (ie its only underlying is the base token)
      if( (baseTokenIsToken0 && amt1 == 0) || (!baseTokenIsToken0 && amt0 == 0) ) return tickIndex;
    }
    // all ticks are below price
    return ticks.length;
  }


  /// @notice Get deposit fee
  /// @param increaseToken0 Whether (token0 added || token1 removed) or not
  /// @dev Simple linear model: from baseFeeX4 / 2 to baseFeeX4 * 3 / 2
  /// @dev Call before withdrawing from ticks or reserves will both be 0
  function getAdjustedBaseFee(bool increaseToken0) public view returns (uint adjustedBaseFeeX4) {
    uint baseFeeX4_ = uint(baseFeeX4);
    (uint res0, uint res1, ) = getReserves();
    uint value0 = res0 * oracle.getAssetPrice(address(token0)) / 10**token0.decimals();
    uint value1 = res1 * oracle.getAssetPrice(address(token1)) / 10**token1.decimals();

    if (increaseToken0)
      adjustedBaseFeeX4 = baseFeeX4_ * value0 / (value1 + 1);
    else
      adjustedBaseFeeX4 = baseFeeX4_ * value1 / (value0 + 1);

    // Adjust from -50% to +50%
    if (adjustedBaseFeeX4 < baseFeeX4_ / 2) adjustedBaseFeeX4 = baseFeeX4_ / 2;
    if (adjustedBaseFeeX4 > baseFeeX4_ * 3 / 2) adjustedBaseFeeX4 = baseFeeX4_ * 3 / 2;
  }


  /// @notice fallback: deposit unless it's WETH being unwrapped
  receive() external payable {
    if(msg.sender != address(WETH)) deposit(address(WETH), msg.value);
  }
  
}  