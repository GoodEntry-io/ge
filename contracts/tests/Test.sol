// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.19;

import "../PositionManager/PositionManager.sol";
import "../PositionManager/LonggPositionManager.sol";
import "../PositionManager/OptionsPositionManager.sol";
import "../helper/ZapBox.sol";

/// @notice Extend LonggPositionManager to test interal function inaccessible code branches
contract Test_LonggPositionManager is LonggPositionManager {

  /// @param roerouter address of the ROE pools router
  constructor(address roerouter) LonggPositionManager(roerouter) {}
  
  /// @notice test internal function validateValuesAgainstOracle
  function test_validateValuesAgainstOracle(IPriceOracle oracle, address assetA, uint amountA, address assetB, uint amountB) external view { 
    validateValuesAgainstOracle(oracle, assetA, amountA, assetB, amountB);
  }
  
  /// @notice test internal function getTargetAmountFromOracle
  function test_getTargetAmountFromOracle(IPriceOracle oracle, address assetA, uint amountA, address assetB) external view returns (uint amountB) {
    amountB = getTargetAmountFromOracle(oracle, assetA, amountA, assetB);
  }
}



/// @notice Extend ZapBox to test interal function inaccessible code branches
contract Test_ZapBox is ZapBox {

  /// @param roerouter address of the ROE pools router
  constructor(address roerouter) ZapBox(roerouter) {}

  /// @notice test internal function cleanupEth
  function test_cleanupEth() external {
    cleanupEth();
  }
}



/// @notice Extend PositionManager to test interal function inaccessible code branches
contract Test_PositionManager is PositionManager {

  /// @param roerouter address of the ROE pools router
  constructor(address roerouter) PositionManager(roerouter) {}
  
  /// @notice test internal function getPoolAddresses
  function test_getPoolAddresses(uint poolId) 
    external view 
    returns( ILendingPool lp, IPriceOracle oracle, IUniswapV2Router01 router, address token0, address token1) 
  {
    (lp, oracle, router, token0, token1) = getPoolAddresses(poolId);
  }
  
  /// @notice test internal function checkSetAllowance
  function test_checkSetAllowance(address token, address spender, uint amount) external {
    checkSetAllowance(token, spender, amount);
  }

  function test_cleanup(ILendingPool LP, address user, address asset) external {
    cleanup(LP, user, asset);
  }
    
}



/// @notice Extend OptionsPositionManager to test interal function inaccessible code branches
contract Test_OptionsPositionManager is OptionsPositionManager {

  /// @param roerouter address of the ROE pools router
  constructor(address roerouter) OptionsPositionManager(roerouter) {}
  
  /// @notice test internal function checkExpectedBalances
  function test_checkExpectedBalances(address debtAsset, uint debtAmount, uint token0Amount, uint token1Amount) external view {
    checkExpectedBalances(debtAsset, debtAmount, token0Amount, token1Amount);
  }
  
  /// @notice test internal function swapTokensForExactTokens
  function test_swapTokensForExactTokens(IUniswapV2Router01 ammRouter, uint recvAmount, uint maxAmount, address[] memory path) external {
    swapTokensForExactTokens(ammRouter, recvAmount, maxAmount, path);
  }
  
  /// @notice test internal function swapTokensForExactTokens
  function test_getTargetAmountFromOracle(IPriceOracle oracle, address assetA, uint amountA, address assetB)  external view returns (uint){
    return getTargetAmountFromOracle(oracle, assetA, amountA, assetB) ;
  }
}