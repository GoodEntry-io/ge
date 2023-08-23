// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.19;

import "../interfaces/INonfungiblePositionManager.sol";
import "../interfaces/IUniswapV3Factory.sol";
import "../interfaces/IUniswapV3Pool.sol";
import "./openzeppelin-solidity/contracts/token/ERC20/ERC20.sol";
import "./openzeppelin-solidity/contracts/token/ERC20/utils/SafeERC20.sol";
import "./openzeppelin-solidity/contracts/utils/Strings.sol";
import "./openzeppelin-solidity/contracts/security/ReentrancyGuard.sol";
import "./lib/LiquidityAmounts.sol";
import "./lib/TickMath.sol";
import "./lib/Sqrt.sol";
import "../interfaces/IAaveOracle.sol";
import "./RoeRouter.sol";


/// @notice Tokenize a Uniswap V3 NFT position
contract TokenisableRange is ERC20("", ""), ReentrancyGuard {
  using SafeERC20 for ERC20;
  /// EVENTS
  event InitTR(address asset0, address asset1, uint128 startX10, uint128 endX10);
  event Deposit(address sender, uint trAmount);
  event Withdraw(address sender, uint trAmount);
  event ClaimFees(uint fee0, uint fee1);
  
  /// VARIABLES

  int24 public lowerTick;
  int24 public upperTick;
  uint24 public feeTier;
  uint128 public liquidity;
  
  uint256 public tokenId;
  uint256 public fee0;
  uint256 public fee1;
  
  struct ASSET {
    ERC20 token;
    uint8 decimals;
  }
  
  ASSET public TOKEN0;
  ASSET public TOKEN1;
  IAaveOracle public ORACLE;
  
  string _name;
  string _symbol;
  
  enum ProxyState { INIT_PROXY, INIT_LP, READY }
  ProxyState public status;
  address private creator;
  
  // @notice deprecated, keep to avoid beacon storage slot overwriting errors
  address public TREASURY_DEPRECATED = 0x22Cc3f665ba4C898226353B672c5123c58751692;
  uint public treasuryFee_deprecated = 20;
  
  // These are constant across chains - https://docs.uniswap.org/protocol/reference/deployments
  INonfungiblePositionManager constant public POS_MGR = INonfungiblePositionManager(0xC36442b4a4522E871399CD717aBDD847Ab11FE88); 
  IUniswapV3Factory constant public V3_FACTORY = IUniswapV3Factory(0x1F98431c8aD98523631AE4a59f267346ea31F984); 
  address constant public treasury = 0x22Cc3f665ba4C898226353B672c5123c58751692;
  uint constant public treasuryFee = 20;
  address constant roerouter = 0x22Cc3f665ba4C898226353B672c5123c58751692;
  uint128 constant UINT128MAX = type(uint128).max;


  /// @notice Store range parameters
  /// @param _oracle Address of the IAaveOracle interface of the ROE lending pool
  /// @param asset0 Quote token address
  /// @param asset1 Base token address 
  /// @param startX10 Range lower price scaled by 1e10
  /// @param endX10 Range high price scaled by 1e10
  /// @param startName Name of the range lower bound 
  /// @param endName Name of the range higher bound
  /// @param isTicker Range is single tick liquidity around upperTick/startX10/startName
  function initProxy(IAaveOracle _oracle, ERC20 asset0, ERC20 asset1, uint128 startX10, uint128 endX10, string memory startName, string memory endName, bool isTicker) external {
    require(address(_oracle) != address(0x0), "Invalid oracle");
    require(status == ProxyState.INIT_PROXY, "!InitProxy");
    creator = msg.sender;
    status = ProxyState.INIT_LP;
    ORACLE = _oracle;
    
    TOKEN0.token    = asset0;
    TOKEN0.decimals = asset0.decimals();
    TOKEN1.token     = asset1;
    TOKEN1.decimals  = asset1.decimals();
    string memory quoteSymbol = asset0.symbol();
    string memory baseSymbol  = asset1.symbol();
        
    int24 _upperTick = TickMath.getTickAtSqrtRatio( uint160( 2**48 * Sqrt.sqrt( (2 ** 96 * (10 ** TOKEN1.decimals)) * 1e10 / (uint256(startX10) * 10 ** TOKEN0.decimals) ) ) );
    int24 _lowerTick = TickMath.getTickAtSqrtRatio( uint160( 2**48 * Sqrt.sqrt( (2 ** 96 * (10 ** TOKEN1.decimals)) * 1e10 / (uint256(endX10  ) * 10 ** TOKEN0.decimals) ) ) );
    
    if (isTicker) { 
      feeTier   = 5;
      int24 midleTick;
      midleTick = (_upperTick + _lowerTick) / 2;
      _upperTick = (midleTick + int24(feeTier)) - (midleTick + int24(feeTier)) % int24(feeTier * 2);
      _lowerTick = _upperTick - int24(feeTier) - int24(feeTier);
      _name     = string(abi.encodePacked("Ticker ", baseSymbol, " ", quoteSymbol, " ", startName, "-", endName));
     _symbol    = string(abi.encodePacked("T-",startName,"_",endName,"-",baseSymbol,"-",quoteSymbol));
    } else {
      feeTier   = 5;
      _lowerTick = (_lowerTick + int24(feeTier)) - (_lowerTick + int24(feeTier)) % int24(feeTier * 2);
      _upperTick = (_upperTick + int24(feeTier)) - (_upperTick + int24(feeTier)) % int24(feeTier * 2);
      _name     = string(abi.encodePacked("Ranger ", baseSymbol, " ", quoteSymbol, " ", startName, "-", endName));
      _symbol   = string(abi.encodePacked("R-",startName,"_",endName,"-",baseSymbol,"-",quoteSymbol));
    }
    lowerTick = _lowerTick;
    upperTick = _upperTick;
    emit InitTR(address(asset0), address(asset1), startX10, endX10);
  }
  

  /// @notice Get the name of this contract token
  /// @dev Override name, symbol and decimals from ERC20 inheritance
  function name()     public view virtual override returns (string memory) { return _name; }
  /// @notice Get the symbol of this contract token
  function symbol()   public view virtual override returns (string memory) { return _symbol; }


  /// @notice Initialize a TokenizableRange by adding assets in the underlying Uniswap V3 position
  /// @param n0 Amount of quote token added
  /// @param n1 Amount of base token added
  /// @notice The token amounts must be 95% correct or this will fail the Uniswap slippage check
  function init(uint n0, uint n1) external {
    require(status == ProxyState.INIT_LP, "!InitLP");
    require(msg.sender == creator, "Unallowed call");
    status = ProxyState.READY;
    TOKEN0.token.safeTransferFrom(msg.sender, address(this), n0);
    TOKEN1.token.safeTransferFrom(msg.sender, address(this), n1);
    TOKEN0.token.safeIncreaseAllowance(address(POS_MGR), n0);
    TOKEN1.token.safeIncreaseAllowance(address(POS_MGR), n1);
    (tokenId, liquidity, , ) = POS_MGR.mint( 
      INonfungiblePositionManager.MintParams({
         token0: address(TOKEN0.token),
         token1: address(TOKEN1.token),
         fee: feeTier * 100,
         tickLower: lowerTick,
         tickUpper: upperTick,
         amount0Desired: n0,
         amount1Desired: n1,
         amount0Min: n0 * 95 / 100,
         amount1Min: n1 * 95 / 100,
         recipient: address(this),
         deadline: block.timestamp
      })
    );
    
    // Transfer remaining assets back to user
    TOKEN0.token.safeTransfer( msg.sender,  TOKEN0.token.balanceOf(address(this)));
    TOKEN1.token.safeTransfer(msg.sender, TOKEN1.token.balanceOf(address(this)));
    _mint(msg.sender, 1e18);
    emit Deposit(msg.sender, 1e18);
  }
  
  
  /// @notice Claim the accumulated Uniswap V3 trading fees
  /// @dev In this version, bc compounding fees prevents depositing a fixed liquidity amount, fees arent compounded
  /// but fully sent to a vault if it exists, else sent to treasury
  function claimFee() public {
    (uint256 newFee0, uint256 newFee1) = POS_MGR.collect( 
      INonfungiblePositionManager.CollectParams({
        tokenId: tokenId,
        recipient: address(this),
        amount0Max: UINT128MAX,
        amount1Max: UINT128MAX
      })
    );
    // If there's no new fees generated, skip compounding logic;
    if ((newFee0 == 0) && (newFee1 == 0)) return;  
    uint tf0 = newFee0 * treasuryFee / 100;
    uint tf1 = newFee1 * treasuryFee / 100;
    if (tf0 > 0) TOKEN0.token.safeTransfer(treasury, tf0);
    if (tf1 > 0) TOKEN1.token.safeTransfer(treasury, tf1);
    
    address vault;
    // Call vault address in a try/catch structure as it's defined as a constant, not available in testing
    if (roerouter.code.length > 0) {
      try RoeRouter(roerouter).getVault(address(TOKEN0.token), address(TOKEN0.token)) returns (address _vault) {
        vault = _vault;
      }
      catch {}
    }
    
    if (vault == address(0x0)) vault = treasury; // if case vault doesnt exist send to treasury
    tf0 = TOKEN0.token.balanceOf(address(this));
    if (tf0 > 0) TOKEN0.token.safeTransfer(vault, tf0);
    tf1 = TOKEN1.token.balanceOf(address(this));
    if (tf1 > 0) TOKEN1.token.safeTransfer(vault, tf1);
    emit ClaimFees(newFee0, newFee1);
  }
  
  
  /// @notice Deposit assets into the range
  /// @param n0 Amount of quote asset
  /// @param n1 Amount of base asset
  /// @return lpAmt Amount of LP tokens created
  function deposit(uint256 n0, uint256 n1) external returns (uint256 lpAmt) {
    lpAmt = depositExactly(n0, n1, 0);
  }
  
  
  /// @notice Deposit assets and get exactly the expected liquidity
  /// @dev If the returned liquidity is very small (=its underlying tokens are both 0), we can round the amount of
  /// liquidity minted. It is possible to abuse this to inflate the supply, but the gain would be several orders of magnitude
  /// lower that the necessary gas cost
  function depositExactly(uint256 n0, uint256 n1, uint256 expectedAmount) public nonReentrant returns (uint256 lpAmt) {
    // Once all assets were withdrawn after initialisation, this is considered closed
    // Prevents TR oracle values from being too manipulatable by emptying the range and redepositing 
    require(totalSupply() > 0, "TR Closed"); 
    
    claimFee();
    TOKEN0.token.safeTransferFrom(msg.sender, address(this), n0);
    TOKEN1.token.safeTransferFrom(msg.sender, address(this), n1);
    TOKEN0.token.safeIncreaseAllowance(address(POS_MGR), n0);
    TOKEN1.token.safeIncreaseAllowance(address(POS_MGR), n1);

    // New liquidity is indeed the amount of liquidity added, not the total, despite being unclear in Uniswap doc
    (uint128 newLiquidity, uint256 added0, uint256 added1) = POS_MGR.increaseLiquidity(
      INonfungiblePositionManager.IncreaseLiquidityParams({
        tokenId: tokenId,
        amount0Desired: n0,
        amount1Desired: n1,
        amount0Min: n0 * 95 / 100,
        amount1Min: n1 * 95 / 100,
        deadline: block.timestamp
      })
    );
    
    uint256 feeLiquidity;
    if (fee0 > 0 || fee1 > 0){
      uint256 TOKEN0_PRICE = ORACLE.getAssetPrice(address(TOKEN0.token));
      uint256 TOKEN1_PRICE = ORACLE.getAssetPrice(address(TOKEN1.token));
      require (TOKEN0_PRICE > 0 && TOKEN1_PRICE > 0, "Invalid Oracle Price");
      // Calculate the equivalent liquidity amount of the non-yet compounded fees
      // Assume linearity for liquidity in same tick range; calculate feeLiquidity equivalent and consider it part of base liquidity 
      uint token0decimals = TOKEN0.decimals;
      uint token1decimals = TOKEN1.decimals;
      feeLiquidity = newLiquidity * ( (fee0 * TOKEN0_PRICE / 10 ** token0decimals) + (fee1 * TOKEN1_PRICE / 10 ** token1decimals) )   
                                    / ( (added0   * TOKEN0_PRICE / 10 ** token0decimals) + (added1   * TOKEN1_PRICE / 10 ** token1decimals) ); 
    }
    lpAmt = totalSupply() * newLiquidity / (liquidity + feeLiquidity); 
    liquidity = liquidity + newLiquidity;
    
    // Round added liquidity up to expectedAmount if the difference is dust
    // ie. underlying amounts of liquidity difference is 0, or value is lower than 1 unit of token0 or token1
    if (lpAmt < expectedAmount){
      uint missingLiq = expectedAmount - lpAmt;
      uint missingLiqValue = missingLiq * latestAnswer() / 1e18;
      (uint u0, uint u1) = getTokenAmounts(missingLiq);
      uint val0 = u0 * ORACLE.getAssetPrice(address(TOKEN0.token)) / 10**TOKEN0.decimals;
      uint val1 = u1 * ORACLE.getAssetPrice(address(TOKEN1.token)) / 10**TOKEN1.decimals;
      // missing liquidity has no value, or underlying amount is 1 or less (meaning some 1 unit rounding error on low decimal tokens)
      if (missingLiqValue == 0 || (u0 <= 1 && u1 <= 1)){
        lpAmt = expectedAmount;
      }
      (u0, u1) = getTokenAmountsExcludingFees(expectedAmount);
    }
    _mint(msg.sender, lpAmt);
    if (n0 > added0) TOKEN0.token.safeTransfer(msg.sender, n0 - added0);
    if (n1 > added1) TOKEN1.token.safeTransfer(msg.sender, n1 - added1);
    emit Deposit(msg.sender, lpAmt);
  }
  
  
  /// @notice Withdraw assets from a range
  /// @param lp Amount of tokens withdrawn
  /// @param amount0Min Minimum amount of quote token withdrawn
  /// @param amount1Min Minimum amount of base token withdrawn
  function withdraw(uint256 lp, uint256 amount0Min, uint256 amount1Min) external nonReentrant returns (uint256 removed0, uint256 removed1) {
    claimFee();
    uint removedLiquidity = uint(liquidity) * lp / totalSupply();
    
    _burn(msg.sender, lp);
    (removed0, removed1) = POS_MGR.decreaseLiquidity(
      INonfungiblePositionManager.DecreaseLiquidityParams({
        tokenId: tokenId,
        liquidity: uint128(removedLiquidity),
        amount0Min: amount0Min,
        amount1Min: amount1Min,
        deadline: block.timestamp
      })
    );
    liquidity = uint128(uint256(liquidity) - removedLiquidity); 
    if (removed0 > 0 || removed1 > 0){
      POS_MGR.collect( 
        INonfungiblePositionManager.CollectParams({
          tokenId: tokenId,
          recipient: msg.sender,
          amount0Max: uint128(removed0),
          amount1Max: uint128(removed1)
        })
      );
    }
    emit Withdraw(msg.sender, lp);
  }
  

  /// @notice Calculate the balance of underlying assets based on the assets price
  /// @param TOKEN0_PRICE Base token price
  /// @param TOKEN1_PRICE Quote token price
  function returnExpectedBalanceWithoutFees(uint TOKEN0_PRICE, uint TOKEN1_PRICE) internal view returns (uint256 amt0, uint256 amt1) {
    // if 0 get price from oracle
    if (TOKEN0_PRICE == 0) TOKEN0_PRICE = ORACLE.getAssetPrice(address(TOKEN0.token));
    if (TOKEN1_PRICE == 0) TOKEN1_PRICE = ORACLE.getAssetPrice(address(TOKEN1.token));

    (amt0, amt1) = LiquidityAmounts.getAmountsForLiquidity(
      uint160(Sqrt.sqrt((TOKEN0_PRICE * 10**TOKEN1.decimals * 2**96) / (TOKEN1_PRICE * 10**TOKEN0.decimals )) * 2**48),
      TickMath.getSqrtRatioAtTick(lowerTick), 
      TickMath.getSqrtRatioAtTick(upperTick),
      liquidity
    );
  }
    
    
  /// @notice Calculate the balance of underlying assets based on the assets price, including fees
  function returnExpectedBalance(uint TOKEN0_PRICE, uint TOKEN1_PRICE) public view returns (uint256 amt0, uint256 amt1) {
    (amt0, amt1) = returnExpectedBalanceWithoutFees(TOKEN0_PRICE, TOKEN1_PRICE);
    amt0 += fee0;
    amt1 += fee1;
  }

  /// @notice Return the price of LP tokens based on the underlying assets price
  /// @param TOKEN0_PRICE Base token price
  /// @param TOKEN1_PRICE Quote token price
  function getValuePerLPAtPrice(uint TOKEN0_PRICE, uint TOKEN1_PRICE) public view returns (uint256 priceX1e8) {
    if ( totalSupply() == 0 ) return 0;
    (uint256 amt0, uint256 amt1) = returnExpectedBalance(TOKEN0_PRICE, TOKEN1_PRICE);
    uint totalValue = TOKEN0_PRICE * amt0 / (10 ** TOKEN0.decimals) + amt1 * TOKEN1_PRICE / (10 ** TOKEN1.decimals);
    return totalValue * 1e18 / totalSupply();
  } 

  
  /// @notice Return the price of the LP token
  function latestAnswer() public view returns (uint256 priceX1e8) {
    return getValuePerLPAtPrice(ORACLE.getAssetPrice(address(TOKEN0.token)), ORACLE.getAssetPrice(address(TOKEN1.token)));
  }
  
  
  /// @notice Return the underlying tokens amounts for a given TR balance excluding the fees
  /// @param amount Amount of tokens we want the underlying amounts for
  function getTokenAmountsExcludingFees(uint amount) public view returns (uint token0Amount, uint token1Amount){
    address pool = V3_FACTORY.getPool(address(TOKEN0.token), address(TOKEN1.token), feeTier * 100);
    (uint160 sqrtPriceX96,,,,,,)  = IUniswapV3Pool(pool).slot0();
    (token0Amount, token1Amount) = LiquidityAmounts.getAmountsForLiquidity( sqrtPriceX96, TickMath.getSqrtRatioAtTick(lowerTick), TickMath.getSqrtRatioAtTick(upperTick),  uint128 ( uint(liquidity) * amount / totalSupply() ) );
  }


  /// @notice Return the underlying tokens amounts for a given TR balance
  /// @param amount Amount of tokens we want the underlying amounts for
  function getTokenAmounts(uint amount) public view returns (uint token0Amount, uint token1Amount){
    (token0Amount, token1Amount) = getTokenAmountsExcludingFees(amount);
    token0Amount += fee0 * amount / totalSupply();
    token1Amount += fee1 * amount / totalSupply();
  }
}