// SPDX-License-Identifier: none
pragma solidity 0.8.19;

import "./PositionManager.sol";

contract LonggPositionManager is PositionManager {
  using SafeERC20 for IERC20;

  ////////////////////// EVENTS
  event OpenPosition(address indexed user, address indexed asset, uint amount, uint value);
  event ClosePosition(address indexed user, address indexed asset, uint amount);
  event LiquidatePosition(address indexed user, address indexed asset, uint amount);
  event ReducedPosition(address indexed user, address indexed asset, uint amount);


  ////////////////////// VARS
  uint constant public HF_MAX = 105e16; // Debt repayment cannot excessively reduce debt
  uint constant private BIGUINT = 2**254;
  
  struct LevParam {
    ILendingPool lendingPool;
    IUniswapV2Router01 ammRouter;
    address user;
    address assetSold;
    uint amountSold;
    IPriceOracle oracle;
  }

  struct DelevParam {
    ILendingPool lendingPool;
    IPriceOracle oracle;
    IUniswapV2Router01 ammRouter;
    address user;
    address debtAsset;
    uint repayAmount;
    address remainingAsset;
    address assetA;
    uint amtA;
    address assetB;
    uint amtB;
    address flashAsset;
    uint flashAmount;
  }
  
  
  ////////////////////// GENERAL   

  /// @param roerouter Address of Roe whitelist router
  constructor (address roerouter) PositionManager(roerouter) {}


  ////////////////////// DISPATCHER
  
  /**
   * @notice Executes an operation after receiving the flash-borrowed asset (open a leverage position or liquidate a position)
   * @param assets The address of the flash-borrowed asset
   * @param amounts The amount of the flash-borrowed asset
   * @param premiums The fee of the flash-borrowed asset
   * @param initiator The address of the flashloan initiator
   * @param params The byte-encoded params passed when initiating the flashloan
   * @return True if the execution of the operation succeeds, false otherwise
   */
  function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,
    bytes calldata params
  ) override external returns (bool) {
    uint8 mode = abi.decode(params, (uint8) );
    if ( mode == 0 ){
      LevParam memory param;
      uint poolId;
      (, param.user, param.assetSold, param.amountSold, , poolId) = abi.decode(params, (uint8, address, address, uint, address, uint));
      address token0;
      address token1;
      (param.lendingPool, param.oracle, param.ammRouter, token0, token1) = getPoolAddresses(poolId);
      require( msg.sender == address(param.lendingPool), "LPM: Call Unallowed");
      sanityCheckUnderlying(assets[0], token0, token1);
      return executeOperationLeverage(assets[0], amounts[0], param);
    }
    else {
      DelevParam memory param;
      uint poolId;
      (, param.user, param.debtAsset, param.repayAmount, param.remainingAsset, poolId) = abi.decode(params, (uint8, address, address, uint, address, uint) );
      param.flashAsset = assets[0];
      param.flashAmount = amounts[0];
      address token0;
      address token1;
      (param.lendingPool, param.oracle, param.ammRouter, token0, token1) = getPoolAddresses(poolId);
      
      require( msg.sender == address(param.lendingPool), "LPM: Call Unallowed");
      sanityCheckUnderlying(assets[0], token0, token1);
      
      (param.assetA, param.amtA, param.assetB, param.amtB) = prepareParams(address(param.lendingPool), param.debtAsset, param.user);
      checkSetAllowance(assets[0], address(param.lendingPool), amounts[0]);

      return executeOperationLiquidate(param);
    }
  }
  
  /// @notice Populate and checks asset parameters and allowances
  /// @param lendingPool Address of the lending pool
  /// @param debtAsset  Asset borrowed
  /// @param user Debt owner
  /// @return assetA Borrowed LP underlying asset A
  /// @return amtA Amount of underlying asset A
  /// @return assetB Borrowed LP underlying asset B
  /// @return amtB Amount of underlying asset B 
  function prepareParams(address lendingPool, address debtAsset, address user) internal returns (address assetA, uint amtA, address assetB, uint amtB) {
    assetA = IUniswapV2Pair(debtAsset).token0();
    assetB = IUniswapV2Pair(debtAsset).token1();
    amtA = IERC20( ILendingPool(lendingPool).getReserveData(assetA).aTokenAddress).balanceOf(user);
    amtB = IERC20( ILendingPool(lendingPool).getReserveData(assetB).aTokenAddress).balanceOf(user);

    IUniswapV2Pair(debtAsset).sync(); // Syncs the pool as underlying balances may not be accurate, which in turn would result in wrong debt calculation
    
    // Check here that allowance is large enough, should happen only once in a lifetime
    checkSetAllowance(debtAsset, lendingPool, BIGUINT);
    checkSetAllowance(assetA, lendingPool, BIGUINT);
    checkSetAllowance(assetB, lendingPool, BIGUINT);
  }


  ////////////////////// OPEN POSITION
  
  /// @notice Open or increase position
  /// @param flashAsset Asset to borrow
  /// @param flashAmount Amount to borrow
  /// @param param Leverage parameters transmitted through the flashloan operation
  /// @return result True if operation succeeds
  function executeOperationLeverage(
    address flashAsset,
    uint256 flashAmount,
    LevParam memory param
  ) 
    private returns (bool result)
  {
    address token0 = IUniswapV2Pair(flashAsset).token0();
    address token1 = IUniswapV2Pair(flashAsset).token1();
    checkSetAllowance(token0, address(param.lendingPool), BIGUINT);
    checkSetAllowance(token1, address(param.lendingPool), BIGUINT);
    checkSetAllowance(flashAsset, address(param.ammRouter), flashAmount);
    
    // Remove Liquidity and get underlying tokens
    (uint256 amount0, uint256 amount1) = param.ammRouter.removeLiquidity(
      token0,
      token1,
      flashAmount,
      0,
      0,
      address(this),
      block.timestamp
    );
    // make sure we not been sandwiched
    validateValuesAgainstOracle(param.oracle, token0, amount0, token1, amount1);
    
    // Swapping some assets
    if ( param.assetSold != address(0x0) ){
      address[] memory path = new address[](2);
      uint amount;
      path[0] = param.assetSold;
      if (param.assetSold == token0){
        path[1] = token1;
        amount = amount0 * param.amountSold / 100;
      }
      else if (param.assetSold == token1){
        path[1] = token0;
        amount = amount1 * param.amountSold / 100;
      }
      else {
        revert("LPM: Invalid Swap Source");
      }
      checkSetAllowance(param.assetSold, address(param.ammRouter), amount);

      param.ammRouter.swapExactTokensForTokens(
        amount,
        getTargetAmountFromOracle(param.oracle, path[0], amount, path[1]) * 99 / 100, // allow 1% slippage
        path,
        address(this),
        block.timestamp
      );

    }
    cleanup (param.lendingPool, param.user, token0);
    cleanup (param.lendingPool, param.user, token1);

    result = true;
  }
  
  /**
    uint valueA = amountA * oracle.getAssetPrice(assetA) / 10**ERC20(assetA).decimals();
    uint valueB = amountB * oracle.getAssetPrice(assetB) / 10**ERC20(assetB).decimals();
    We expect valueA == valueB
  */
  /// @notice Calculate a target swap amount based on oracle-provided token prices
  /// @param oracle Price oracle
  /// @param assetA address of token A
  /// @param amountA Amount of toke A
  /// @param assetB address of token B
  /// @return amountB Amount of target token
  function getTargetAmountFromOracle(IPriceOracle oracle, address assetA, uint amountA, address assetB) 
    internal view returns (uint amountB) 
  {
    uint priceAssetA = oracle.getAssetPrice(assetA);
    uint priceAssetB = oracle.getAssetPrice(assetB);
    require ( priceAssetA > 0 && priceAssetB > 0, "LPM: Invalid Oracle Price");
    amountB = amountA * priceAssetA * 10**ERC20(assetB).decimals() / 10**ERC20(assetA).decimals() / priceAssetB;
    require( amountB > 0, "LPM: Target Amount Too Low");
  }

  
  /// @notice Transfer collateral asset from user to ROE and open a longG position
  /// @param poolId ID of the ROE lending pool
  /// @param collateralAsset The collateral token
  /// @param collateralAmount The collateral amount
  /// @param borrowedAsset The LP asset borrowed
  /// @param borrowedAmount The amount of LP borrowed
  function depositCollateralAndOpen(uint poolId, address collateralAsset, uint collateralAmount, address borrowedAsset, uint borrowedAmount) external {
    (ILendingPool LP,,,,) = getPoolAddresses(poolId);
    IERC20(collateralAsset).safeTransferFrom(msg.sender, address(this), collateralAmount);
    checkSetAllowance(collateralAsset, address(LP), collateralAmount);
    LP.deposit( collateralAsset, collateralAmount, msg.sender, 0 );
    openOneSidedPosition(poolId, borrowedAsset, borrowedAmount, address(0x0), 0);
  }


  /// @notice Open a position by flashloaning assets
  /// @param poolId ID of the ROE lending pool
  /// @param asset The address of the LP token to borrow
  /// @param amount The LP token amount to borrow
  function open(uint poolId, address asset, uint amount) external {
    openOneSidedPosition(poolId, asset, amount, address(0x0), 0);
  }


  /// @notice Open a position by flashloaning assets
  /// @param poolId ID of the ROE lending pool
  /// @param asset LP asset borrowed
  /// @param amount amount borrowed: cannot be larger than 4.7 times the user's collateral available value, check on frontend
  /// @param assetSold If non 0x0, address of the underlying sold
  /// @param amountSoldInPercent Percentage of assets sold, from 0 to 100
  /// @dev Create the params array in a separate function because stack depth then call flash with param
  function openOneSidedPosition(uint poolId, address asset, uint amount, address assetSold, uint amountSoldInPercent) public {  
    require(amountSoldInPercent <= 100, "LPM: Invalid Percentage");
    // mode  = 0 leverage
    bytes memory params = abi.encode(0, msg.sender, assetSold, amountSoldInPercent, address(0x0), poolId);
    flas(poolId, asset, amount, params);
  }
  /// @notice Called by openOneSidedPosition
  function flas(uint poolId, address asset, uint amount, bytes memory params) internal {
    (ILendingPool LP, IPriceOracle PRICE_ORACLE,,, ) = getPoolAddresses(poolId);
    address[] memory assets = new address[](1);
    uint[] memory amounts = new uint[](1);
    uint[] memory flashtype = new uint[](1); 
    assets[0] = asset;
    amounts[0] = amount;
    flashtype[0] = 2; // 2: variable mode debt
    
    //abi.encode(positionMode, ...)
    LP.flashLoan( address(this), assets, amounts, flashtype, msg.sender, params, 0);
    emit OpenPosition(msg.sender, asset, amount, amount * PRICE_ORACLE.getAssetPrice(asset) / 10**ERC20(asset).decimals());
  }
  


  ////////////////////// REDUCING POSITION
  
  /// @notice Repays fully and exactly a user's debt for one borrowed LP using a flashloan. This has a cost and repayDebt should be called if loan isnt needed
  /// @param poolId ID of the ROE lending pool
  /// @param debtAsset the borrowed LP token address
  /// @param repayAmount amount of borrowed tokens to repay; 0 or higher than current debt will repay all
  /// @param remainingAsset Only receive this asset back when closing position
  function closeAndWithdrawCollateral(
    uint poolId, 
    address debtAsset, 
    uint repayAmount, 
    address remainingAsset
  ) 
    external
  {
    clos(poolId, msg.sender, debtAsset, repayAmount, remainingAsset, true);
    
    (ILendingPool lendingPool,,,, ) = getPoolAddresses(poolId);
    (,,,,, uint userHF) = lendingPool.getUserAccountData(msg.sender);
    require(userHF > 1e18, "LPM: HF Too Low");
  }
    
  
  /// @notice Repays fully and exactly a user's debt for one borrowed LP using a flashloan. This has a cost and repayDebt should be called if loan isnt needed
  /// @param poolId ID of the ROE lending pool
  /// @param debtAsset the borrowed LP token address
  /// @param repayAmount amount of borrowed tokens to repay; 0 or higher than current debt will repay all
  /// @param remainingAsset Only receive this asset back when closing position
  function close(
    uint poolId,
    address debtAsset, 
    uint repayAmount, 
    address remainingAsset
  ) 
    external
  {
    clos(poolId, msg.sender, debtAsset, repayAmount, remainingAsset, false);
  }
  
  /// @notice Repays a user's LP token debt
  /// @param poolId ID of the ROE lending pool
  /// @param user Owner of the position closed
  /// @param debtAsset the borrowed LP token address
  /// @param repayAmount amount of borrowed tokens to repay; 0 or higher than current debt will repay all
  /// @param remainingAsset Only receive this asset back when closing position
  /// @param withdrawCollateral True if the user wants to withdraw the position collateral from the lending pool after closing the position
  function clos(
    uint poolId, 
    address user,
    address debtAsset, 
    uint repayAmount, 
    address remainingAsset,
    bool withdrawCollateral
  ) 
    internal
  {
    DelevParam memory param; 
    (param.lendingPool, param.oracle, param.ammRouter, param.assetA, param.assetB) = getPoolAddresses(poolId);
    param.debtAsset = debtAsset;
    param.repayAmount = repayAmount;
    (, param.amtA,, param.amtB) = prepareParams(address(param.lendingPool), param.debtAsset, user);
    require(remainingAsset == param.assetA || remainingAsset == param.assetB, "LPM: Invalid Remaining Asset");
    require(checkDebtAssetAndTokens(debtAsset, param.assetA, param.assetB), "LPM: Invalid Debt Asset");
    
    // Transfer underlying tokens here + withdraw
    PMWithdraw(param.lendingPool, user, param.assetA, param.amtA);
    PMWithdraw(param.lendingPool, user, param.assetB, param.amtB);

    // Calculate how much is needed to repay the debtAsset loan, if one token is not enough
    uint debt = IERC20(param.lendingPool.getReserveData(param.debtAsset).variableDebtTokenAddress ).balanceOf(user);
    require(debt > 0, "LPM: No Debt");
    if ( param.repayAmount > 0 && param.repayAmount < debt ) debt = param.repayAmount;


    (uint debtA, uint debtB) = _calculateDebt(param.debtAsset, debt);

    // Check LP underlying assets value against oracle values to avoid sandwiching: will fail if error > 1%
    validateValuesAgainstOracle(param.oracle, param.assetA, debtA, param.assetB, debtB); 

    // Rebalance if one token is missing
    if ( debtA > param.amtA || debtB > param.amtB){
      rebalanceTokens(param.ammRouter, param.assetA, param.amtA, debtA, param.assetB, param.amtB, debtB, param.debtAsset);
      (debtA, debtB) = _calculateDebt(param.debtAsset, debt);
    }

    // if msg.sender != user, this is a liquidation, send liq. fee to treasury
    if (user != msg.sender) IERC20(remainingAsset).safeTransfer(ROEROUTER.treasury(), (remainingAsset == param.assetA ? debtA/50 : debtB/50) );

    // Step 2: both tokens in sufficient quantity, addLiquidity and return LP
    transferAndMint(param.debtAsset, param.assetA, debtA, param.assetB, debtB, debt );
    param.lendingPool.repay( param.debtAsset, debt, 2, user);

    // Step 3: do we want to keep all of the tokens?
    if (msg.sender == user) {
      if ( remainingAsset == param.assetA ){
        swapAllTokens(param.ammRouter, param.assetB, param.assetA);
      }
      else if (remainingAsset == param.assetB ){
        swapAllTokens(param.ammRouter, param.assetA, param.assetB);
      }
    }
    
    // Step 4: send back funds to user
    if (withdrawCollateral){
      uint remaining = IERC20(remainingAsset).balanceOf(address(this));
      IERC20(remainingAsset).safeTransfer(user, remaining);
    }
    cleanup(param.lendingPool, user, param.assetA);
    cleanup(param.lendingPool, user, param.assetB);
    
    if (msg.sender == user){
      emit ClosePosition(user, param.debtAsset, debt);
    }
    else {
      emit ReducedPosition(param.user, param.debtAsset, debt);
      (,,,,, uint userHF) = param.lendingPool.getUserAccountData(user);
      require(userHF <= HF_MAX, "LPM: Reduce Too Much");
    }
    cleanup(param.lendingPool, user, param.debtAsset);
  }

  
  ////////////////////// LIQUIDATIONS
  
  /// @notice Liquidate up to 50% of an unhealthy position
  /// @param poolId ID of the ROE lending pool
  /// @param user The owner of the loan to liquidate
  /// @param debtAsset The borrowed LP to repay
  /// @param repayAmount The amount of LP to repay
  /// @param collateralAsset The collateral asset to et back as payment
  /// @dev Based on https://docs.aave.com/developers/v/2.0/guides/liquidations#solidity
  /// @dev Flashloan and repay the LP debt, then withdraws the underlying tokens to recreate the LP position in Uniswap
  function liquidate (
    uint poolId, 
    address user,
    address debtAsset,
    uint256 repayAmount,
    address collateralAsset
  )
    external
  {
    address[] memory assets = new address[](1);
    uint[] memory amounts = new uint[](1);
    uint[] memory flashtype = new uint[](1);
    assets[0] = debtAsset;
    amounts[0] = repayAmount;
    flashtype[0] = 0;
    
    bytes memory param = abi.encode( uint(1), user, debtAsset, repayAmount, collateralAsset, poolId); // open: 0, liquidate: 1 
    (ILendingPool lendingPool,,,,) = getPoolAddresses(poolId);
    lendingPool.flashLoan( address(this), assets, amounts, flashtype, address(this), param, 0);

    //Transfer remaining tokens to liquidator
    uint remaining = IERC20(collateralAsset).balanceOf(address(this));
    IERC20(collateralAsset).safeTransfer(msg.sender, remaining);
    cleanup(lendingPool, user, debtAsset);
  }
  
  /// @notice Liquidate operation once flashloan is received
  /// @param param deleverage parameters
  /// @return result Return true if operation completed properly (Aave flashloan requirement)
  /// @dev Recovered tokens are swapped and used to repay flashloan
  function executeOperationLiquidate(DelevParam memory param) private returns (bool result) {
      param.lendingPool.liquidationCall(param.remainingAsset, param.debtAsset, param.user, param.repayAmount, false);
      param.amtA = IERC20(param.assetA).balanceOf(address(this));
      param.amtB = IERC20(param.assetB).balanceOf(address(this));

      uint debt = param.flashAmount;
      (uint debtA, uint debtB) = _calculateDebt(param.debtAsset, debt);
      validateValuesAgainstOracle(param.oracle, param.assetA, debtA, param.assetB, debtB); 
      
      // Obviously 1 token is missing since only 1 collateral is returned , swap to rebalance
      rebalanceTokens(param.ammRouter, param.assetA, param.amtA, debtA, param.assetB, param.amtB, debtB, param.debtAsset);
      (debtA, debtB) = _calculateDebt(param.debtAsset, debt);
      transferAndMint(param.debtAsset, param.assetA, debtA, param.assetB, debtB, debt );
      
      if ( param.remainingAsset == param.assetA ){
        swapAllTokens(param.ammRouter, param.assetB, param.assetA);
      }
      else if (param.remainingAsset == param.assetB ){
        swapAllTokens(param.ammRouter, param.assetA, param.assetB);
      }
      else {
        revert("LPM: Invalid Swap Source");
      }

      emit LiquidatePosition(param.user, param.debtAsset, debt);
      result = true;
  }
  
  
  ////////////////////// GRACEFUL DELEVERAGING
  
  /// @notice Gracefully deleverage a low health LP debt position
  /// @param poolId ID of the ROE lending pool
  /// @param user The owner of the reduced debt
  /// @param debtAsset The borrowed asset to repay
  /// @param repayAmount The amount of LP debt to repay 
  /// @param collateralAsset Collateral asset returned when liquidating the position
  function softLiquidateLP(
    uint poolId, 
    address user,
    address debtAsset,
    uint256 repayAmount, 
    address collateralAsset
  ) external {
    clos(poolId, user, debtAsset, repayAmount, collateralAsset, false);
    
    (ILendingPool lendingPool,,, address token0, address token1) = getPoolAddresses(poolId);
    sanityCheckUnderlying(debtAsset, token0, token1);
    (,,,,, uint userHF) = lendingPool.getUserAccountData(user);
    require(userHF > 1e18, "LPM: HF Too Low");
  }  
  
  
  /// @notice Gracefully deleverage a low health generic debt position
  /// @param poolId ID of the ROE lending pool
  /// @param user The owner of the reduced debt
  /// @param debtAsset The borrowed asset to repay
  /// @param repayAmount The amount of debt to repay 
  /// @param collateralAsset Collateral asset returned when liquidating the position
  function softLiquidate(
    uint poolId, 
    address user,
    address debtAsset,
    uint256 repayAmount, 
    address collateralAsset
  ) external {
    (ILendingPool lendingPool, IPriceOracle oracle,, address token0, address token1) = getPoolAddresses(poolId);
    require(debtAsset == token0 || debtAsset == token1, "LPM: Invalid Debt Asset");
    IERC20(debtAsset).safeTransferFrom(msg.sender, address(this), repayAmount);
    checkSetAllowance(debtAsset, address(lendingPool), repayAmount);

    // Fee is 1% of repayAmount value
    uint feeValueE8 = repayAmount * oracle.getAssetPrice(debtAsset) / 10**ERC20(debtAsset).decimals() / 100;
    uint feeAmount = feeValueE8 * 10**ERC20(collateralAsset).decimals() / oracle.getAssetPrice(collateralAsset);
    
    PMWithdraw(lendingPool, user, collateralAsset, feeAmount);
    IERC20(collateralAsset).safeTransfer(ROEROUTER.treasury(), feeAmount);
    
    lendingPool.repay( debtAsset, repayAmount, 2, user);
    emit ReducedPosition(user, debtAsset, repayAmount);
    (,,,,, uint userHF) = lendingPool.getUserAccountData(user);
    require(userHF <= HF_MAX, "LPM: Excessive Liquidation" );
    require(userHF > 1e18, "LPM: HF Too Low");
  }  


  ////////////////////// DELTA NEUTRALIZE
  
  /// @notice Rebalance a position to make it delta neutral: rebalance risk token to be half the debt
  /// @param poolId ID of the ROE lending pool
  /// @param debtAsset The LP asset borrowed
  /// @param riskAsset The asset the user wants to rebalance to exactly half the debt
  function deltaNeutralize(    
    uint poolId, 
    address debtAsset,
    address riskAsset
  ) external {
    DelevParam memory param; 
    ( param.lendingPool,  param.oracle, param.ammRouter, param.assetA, param.assetB) = getPoolAddresses(poolId);
    (, param.amtA,, param.amtB) = prepareParams(address( param.lendingPool), debtAsset, msg.sender);
    require(checkDebtAssetAndTokens(debtAsset, param.assetA, param.assetB), "LPM: Invalid Debt Asset");
    require(riskAsset == param.assetA || riskAsset == param.assetB, "LPM: Invalid Risk Asset");
    
    uint debt = IERC20( param.lendingPool.getReserveData(debtAsset).variableDebtTokenAddress ).balanceOf(msg.sender);
    require(debt > 0, "LPM: No Debt");
    (uint debtA, uint debtB) = _calculateDebt(debtAsset, debt);
    validateValuesAgainstOracle( param.oracle, param.assetA, debtA, param.assetB, debtB); 

    PMWithdraw( param.lendingPool, msg.sender, param.assetA, param.amtA);
    PMWithdraw( param.lendingPool, msg.sender, param.assetB, param.amtB);
    // If the risky asset is missing (price went down and it now makes up for more of the LP token balance)
    if ( (riskAsset == param.assetA && param.amtA < debtA) || (riskAsset == param.assetB && param.amtB < debtB) ){
      rebalanceTokens( param.ammRouter, param.assetA, param.amtA, debtA, param.assetB, param.amtB, debtB, debtAsset);
    }
    // Too much risky asset as its price went up, rebalance by selling the excess
    // use https://blog.alphaventuredao.io/onesideduniswap/ formula
    else if ( riskAsset == param.assetA && param.amtA > debtA ) {
      (uint resA,,) = IUniswapV2Pair(debtAsset).getReserves();
      swapExactly(param.assetA, param.amtA, debtA, resA, param.assetB,  param.ammRouter);
    }
    else if ( riskAsset == param.assetB && param.amtB > debtB ) {
      (,uint resB,) = IUniswapV2Pair(debtAsset).getReserves();
      swapExactly(param.assetB, param.amtB, debtB, resB, param.assetA,  param.ammRouter);
    }
    
    // Send funds back to user
    cleanup( param.lendingPool, msg.sender, param.assetA);
    cleanup( param.lendingPool, msg.sender, param.assetB);
  }
  
  /// @notice Swap exactly an excess of tokens to match a target
  /// @dev Since the excess depends on the debt, the swap will change the debt, cf calculation article
  function swapExactly(address token0, uint amount, uint debt, uint res, address token1, IUniswapV2Router01 ammRouter) private {
    uint swapAmount = ( amount - debt ) * 10**18 / ( 10**18 + 10**18 * debt * 997 / 1000 / res ); 
    address[] memory path = new address[](2);
    path[0] = token0;
    path[1] = token1;
    if ( IERC20(token0).allowance(address(this), address(ammRouter)) < swapAmount ) IERC20(token0).safeIncreaseAllowance(address(ammRouter), 2**256-1);
    ammRouter.swapExactTokensForTokens(swapAmount, 1, path, address(this), block.timestamp);
  }



 
  ////////////////////// HELPERS

  /// @notice Check that the first address is a LP token with the 2 following underlying tokens
  /// @ param
  function checkDebtAssetAndTokens(address lpToken, address token0, address token1) internal returns (bool isValid){
    isValid = true;
    if(IUniswapV2Pair(lpToken).token0() != token0) isValid = false;
    else if(IUniswapV2Pair(lpToken).token1() != token1) isValid = false;
  }

  
  /// @notice Swap all source tokens from this contract to target token
  /// @param ammRouter The AMM router
  /// @param source The source token
  /// @param target The target token
  function swapAllTokens(IUniswapV2Router01 ammRouter, address source, address target) internal
  {
    uint amount = IERC20(source).balanceOf(address(this));

    if (amount > 0) {
      address[] memory path = new address[](2);
      path[0] = source;
      path[1] = target;
      
      if ( ammRouter.getAmountsOut(amount, path)[1] > 0 ){
        checkSetAllowance(source, address(ammRouter), amount);
        
        ammRouter.swapExactTokensForTokens(
          amount,
          0,
          path,
          address(this),
          block.timestamp
        );
      }
    } 
  }


  /// @notice Rebalance tokens so that the missing token supply is exactly what is needed to repay the LP debt
  /// @param ammRouter The AMM router
  /// @param assetA The first token 
  /// @param balanceA The current balance of assetA
  /// @param debtA The amount of assetA debt
  /// @param assetB The second token
  /// @param balanceB The current balance of assetB
  /// @param debtB The amount of assetB debt
  /// @param debtAsset The LP token address for pair assetA-assetB
  /// @dev Formula derivation: cf. doc
  function rebalanceTokens(
    IUniswapV2Router01 ammRouter,
    address assetA, uint balanceA, uint debtA,
    address assetB, uint balanceB, uint debtB,
    address debtAsset
  ) internal 
  {
    address[] memory path = new address[](2);
    (uint resA, uint resB,) = IUniswapV2Pair(debtAsset).getReserves();
    uint swapAmount;
    uint recvAmount;
    
    if ( balanceA < debtA ){
      swapAmount = 1000 * ( debtA - balanceA ) * resB / 997 / ( balanceA + resA ) + 1;
      recvAmount = 997*resA * swapAmount / (1000*resB + 997 * swapAmount )+1; //+1 for rounding pb
      path[0] = assetB;
      path[1] = assetA;
    }
    else {
      swapAmount = 1000 * ( debtB - balanceB ) * resA / 997 / ( balanceB + resB ) + 1;
      recvAmount = 997*resB * swapAmount / (1000 *resA + 997 * swapAmount )+1;
      path[0] = assetA;
      path[1] = assetB;
    }
    
    swap(ammRouter,
      recvAmount,
      swapAmount * 2,
      path
    );
  }
  
  
  /// @notice Swaps assets for exact assets
  /// @param ammRouter AMM router address
  /// @param recvAmount Amount of target token received
  /// @param maxAmount Amount of source token allowed to be spent minus margin
  /// @param path The path [source, target] of the swap
  function swap(IUniswapV2Router01 ammRouter, uint recvAmount, uint maxAmount, address[] memory path) internal {
    checkSetAllowance(path[0], address(ammRouter), maxAmount);

    ammRouter.swapTokensForExactTokens(
      recvAmount,
      maxAmount,
      path,
      address(this),
      block.timestamp
    );
  }
  
  
  /// @notice Calculate the required amounts of underlying assets A and B to repay debt amount of debtAsset
  /// @param debtAsset the LP token address
  /// @param debt The amount of LP debt
  /// @return debtA Token A debt
  /// @return debtB Token B debt
  function _calculateDebt(address debtAsset, uint debt) internal view returns (uint debtA, uint debtB)
  {
    (uint resA, uint resB,) = IUniswapV2Pair(debtAsset).getReserves();
    uint totalSupply = IUniswapV2Pair(debtAsset).totalSupply();
    
    debtA = debt * resA / totalSupply; 
    if ( debtA * totalSupply / resA < debt ) debtA += 1;// Adding 1 if rounding errors causes large errors in LP
    debtB = debt * resB / totalSupply;
    if ( debtB * totalSupply / resB < debt ) debtB += 1;
  }
  
  
  /// @notice Transfer tokens to Uni pool and mint LP
  /// @param debtAsset The LP token asset
  /// @param assetA The underlying token A
  /// @param amountA The amount of token A to use to mint LP
  /// @param assetB The underlying token B
  /// @param amountB The amount of token B to use to mint LP
  /// @param debt The min amount of LP tokens to mint
  /// @return liquidity The amount of liquidity minted
  function transferAndMint(address debtAsset, address assetA, uint amountA, address assetB, uint amountB, uint debt) internal returns (uint liquidity) {    
    IERC20(assetA).safeTransfer(debtAsset, amountA);
    IERC20(assetB).safeTransfer(debtAsset, amountB);
    liquidity = IUniswapV2Pair(debtAsset).mint(address(this));
    //require(retLiq >= debt, "LPM: LP Mint Mismatch");
  }  
  
  
  /// @notice Check that lp is a LP token matching given tokens or revert
  /// @param lp LP token address
  /// @param token0 Underlying token 0
  /// @param token1 Underlying token 1
  function sanityCheckUnderlying(address lp, address token0, address token1) internal {
    address t0 = IUniswapV2Pair(lp).token0();
    address t1 = IUniswapV2Pair(lp).token1();
    require(token0 == t0 && token1 == t1, "LPM: Invalid LP Asset");
  }
}
