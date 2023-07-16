// SPDX-License-Identifier: none
pragma solidity 0.8.19;

import "./PositionManager.sol";
import "../TokenisableRange.sol";


/**
 * Leverage in and out of a range
 */
contract RangerPositionManager is PositionManager {

  ////////////////////// EVENTS
  event BuyOptions(address indexed user, address indexed asset, uint amount, uint value);
  event ClosePosition(address indexed user, address indexed asset, uint amount);
  event LiquidatePosition(address indexed user, address indexed asset, uint amount);
  event ReducedPosition(address indexed user, address indexed asset, uint amount);



  ////////////////////// GENERAL   

  constructor (address roerouter) PositionManager(roerouter) {}


  ////////////////////// DISPATCHER
  /**
   * @notice Aave-compatible flashloan receiver dispatch: open a leverage position or liquidate a position
   * @param assets The address of the flash-borrowed asset
   * @param amounts The amount of the flash-borrowed asset
   * @param premiums The fee of the flash-borrowed asset
   * @param initiator The address of the flashloan initiator
   * @param params The byte-encoded params passed when initiating the flashloan
   * @return result True if the execution of the operation succeeds, false otherwise
   */
  function executeOperation(
    address[] calldata assets,
    uint256[] calldata amounts,
    uint256[] calldata premiums,
    address initiator,
    bytes calldata params
  ) override external returns (bool result) {
    execute(assets, amounts, params);
    result = true;
  }
  
  /// @notice Localize function to avoid stack too deep
  function execute(
    address[] calldata assets,
    uint256[] calldata amounts,
    bytes calldata params
  ) internal
  {
    (uint poolId, uint8 mode, address user, address range) = abi.decode(params, (uint, uint8, address, address));
    
    (ILendingPool LP,,,,) = getPoolAddresses(poolId);
    require(msg.sender == address(LP), "RPM: Call Unallowed");

    // Lev.farm a RANGER
    if (mode == 0){
      checkSetAllowance(assets[0], range, amounts[0]);
      checkSetAllowance(assets[1], range, amounts[1]);
      TokenisableRange(range).deposit(amounts[0], amounts[1]);
    }
    // Lev.farm full range LPv2 
    else if (mode == 1) {
      depositV2Liquidity(poolId, assets[0], amounts[0], assets[1], amounts[1]);
    }
    cleanup(LP, user, range);
    cleanup(LP, user, assets[0]);
    cleanup(LP, user, assets[1]);
  }
  
  /// @notice Deposit liquidity in a UNIv2 pair
  /// @param poolId Roe Router Pool ID
  /// @param token0 Token0
  /// @param amount0 Amount of token 0
  /// @param token1 Token1
  /// @param amount1 Amount of token 1
  /// @dev Max slippage 1%
  function depositV2Liquidity(uint poolId, address token0, uint amount0, address token1, uint amount1) internal {
    (,, IUniswapV2Router01 router,,) = getPoolAddresses(poolId);
    checkSetAllowance(token0, address(router), amount0);
    checkSetAllowance(token1, address(router), amount1);
    router.addLiquidity(token0, token1, amount0, amount1, amount0*99/100 , amount1*99/100, address(this), block.timestamp);
  }
  
  
  /// @notice Farm a range
  /// @param poolId ID of the ROE lending pool
  /// @param range Address of the Ranger
  /// @param tokenAmounts Amounts of underlying tokens
  /// @dev Note that calling the flashloan directly rather than using this functions works too and avoids needing to creditDelegate
  function farmRange(
    uint poolId, 
    address range,
    uint[] memory tokenAmounts
  )
    external
  {
    require(range != address(0x0), "RPM: Invalid Range");
    require(tokenAmounts.length == 2, "RPM: Invalid Amounts");
    bytes memory params = abi.encode(poolId, uint8(0), msg.sender, range);
    (ILendingPool LP,,, address token0, address token1) = getPoolAddresses(poolId);

    address[] memory assets = new address[](2);
    assets[0] = token0;
    assets[1] = token1;

    uint[] memory flashtype = new uint[](2);
    flashtype[0] = 2;
    flashtype[1] = 2;
    LP.flashLoan( address(this), assets, tokenAmounts, flashtype, msg.sender, params, 0);
  }


  /// @notice Close [partially] a position and repay if necessary underlying token debts
  /// @param poolId ID of the ROE lending pool
  /// @param user Position owner (differs from msg.sender in case of liquidation)
  /// @param range Address of the Ranger
  /// @param liquidity Amount of Ranger to withdraw and close
  /// @dev Useful if user took underlying token debt to leverage farm, so repay underlying token debt before returning excess tokens
  function closeRange(
    uint poolId,
    address user,
    address range,
    uint liquidity
  )
    external
 {
    (ILendingPool LP, IPriceOracle oracle, IUniswapV2Router01 router, address token0, address token1) = getPoolAddresses(poolId);
    PMWithdraw(LP, user, range, liquidity);
    uint amount0;
    uint amount1;
    // if repaying a UNIv2 LP debt
    if ( IUniswapV2Factory(router.factory()).getPair(token0, token1) == range ){
      checkSetAllowance(range, address(router), liquidity);
      
      (uint removed0, uint removed1) = router.removeLiquidity(
        token0, 
        token1, 
        liquidity, 
        0, 
        0, 
        address(this),
        block.timestamp
      );
      // if sandwich, both tokens values should not be equivalent when checked against the oracle
      validateValuesAgainstOracle(oracle, token0, removed0, token1, removed1);
    }
    // else: Tokenisable Range
    else {
      (amount0, amount1) = TokenisableRange(range).getTokenAmounts(liquidity);
      (uint removed0, uint removed1) = TokenisableRange(range).withdraw(liquidity, 0, 0);
      require(
        removed0 * oracle.getAssetPrice(token0) / 10**ERC20(token0).decimals()
        + removed1 * oracle.getAssetPrice(token1) / 10**ERC20(token1).decimals()
        >= TokenisableRange(range).latestAnswer() * liquidity / 1e18 * 98 / 100,
        "RPM: CR Slippage"
      );
    }

    // if msg.sender != user, it's a liquidation, send liquidation fee.
    // LP will revert if position isnt liquidable
    if ( msg.sender != user ){
      if (amount0 / 100 > 0) LP.deposit(token0, amount0 / 100, msg.sender, 0);
      if (amount1 / 100 > 0) LP.deposit(token1, amount1 / 100, msg.sender, 0);
    }

    // Use any remaining tokens to repay outstanding debt and/or deposit in ROE
    cleanup(LP, user, token0);
    cleanup(LP, user, token1);
  }
}