// SPDX-License-Identifier: none
pragma solidity 0.8.19;

import "../openzeppelin-solidity/contracts/token/ERC20/ERC20.sol";
import "../openzeppelin-solidity/contracts/token/ERC20/utils/SafeERC20.sol";
import "../openzeppelin-solidity/contracts/security/ReentrancyGuard.sol";
import "../../interfaces/IUniswapV2Router01.sol";
import "../../interfaces/IUniswapV2Factory.sol";
import "../../interfaces/IUniswapV2Pair.sol";
import {ILendingPool} from "../../interfaces/IAaveLendingPoolV2.sol";
import {IPriceOracle} from "../../interfaces/IPriceOracle.sol";
import {ILendingPoolAddressesProvider} from "../../interfaces/ILendingPoolAddressesProvider.sol";
import "../RoeRouter.sol";


interface ERC2612 {
  function permit(address owner, address spender, uint256 value, uint256 deadline, uint8 v, bytes32 r, bytes32 s) external;
}


contract ZapBox is ReentrancyGuard {
  using SafeERC20 for ERC20;
  RoeRouter public ROEROUTER; // set to immutable after coverage tests are done
  
  /// EVENTS
  event ZapIn(address lendingPool, address lpToken, uint amount);
  event ZapOut(address lendingPool, address lpToken, uint amount);
  

  constructor(address roeRouter) {
    require(roeRouter != address(0x0), "Invalid Address");
    ROEROUTER = RoeRouter(roeRouter);
  }
  
  
  /// EIP-2612 permit parameters
  struct PermitParam {
    address owner;
    address spender;
    uint value;
    uint deadline;
    uint8 v;
    bytes32 r;
    bytes32 s;
  }

  /////// ZAP FUNCTIONS


  /// @notice Add liquidity to a Uniswap pool then add the LP tokens to the ROE pool
  /// @param poolId Id of the ROE pool
  /// @param token0 Underlying token for lpToken
  /// @param amount0 Amount of token0 to add to the AMM pool
  /// @param token1 Underlying token for lpToken
  /// @param amount1 Amount of token1 to add to the AMM pool
  /// @return amountA Amount of token added
  /// @return amountB Amount of token added
  /// @return liquidity LP amount created
  /// @dev Slippage is fixed and set to 1% (min amount of each token added 99%) to prevent sandwiching
  function zapIn(uint poolId, address token0, uint amount0, address token1, uint amount1) 
    external
    nonReentrant()
    returns (uint amountA, uint amountB, uint liquidity)
  {
    
    require(amount0 > 0 && amount1 > 0, "ZB: Zero Amount");
    (ILendingPool lp, IUniswapV2Router01 router,) = getPoolAddresses(poolId);
    address lpToken = IUniswapV2Factory(router.factory()).getPair(token0, token1);

    ERC20(token0).safeTransferFrom(msg.sender, address(this), amount0);
    ERC20(token1).safeTransferFrom(msg.sender, address(this), amount1);
    checkSetApprove(token0, address(router), amount0);
    checkSetApprove(token1, address(router), amount1);
    (amountA, amountB, liquidity) = router.addLiquidity(token0, token1, amount0, amount1, amount0*99/100 , amount1*99/100, address(this), block.timestamp);
    
    checkSetApprove(lpToken, address(lp), liquidity);
    lp.deposit(lpToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), lpToken, liquidity);
    
    cleanup(token0);
    cleanup(token1);
  }


  /// @notice Add liquidity using ETH to a Uniswap pool then add the LP tokens to the ROE pool
  /// @param poolId Id of the ROE pool
  /// @param token0 Underlying token for lpToken
  /// @param amount0 Amount of token0 to add to the AMM pool
  /// @return amountToken Amount of token added
  /// @return amountEth amount of ETH added
  /// @return liquidity LP amount created
  /// @dev Slippage is fixed and set to 1% (min amount of each token added 99%) to prevent sandwiching
  function zapInETH(uint poolId, address token0, uint amount0) 
    external payable 
    nonReentrant()
    returns (uint amountToken, uint amountEth, uint liquidity)
  {
    require(amount0 > 0 && msg.value > 0, "ZB: Zero Amount");
    (ILendingPool lp, IUniswapV2Router01 router,) = getPoolAddresses(poolId);
    address lpToken = IUniswapV2Factory(router.factory()).getPair(router.WETH(), token0);

    ERC20(token0).safeTransferFrom(msg.sender, address(this), amount0);
    checkSetApprove(token0, address(router), amount0);
    
    (amountToken, amountEth, liquidity) = router.addLiquidityETH{value: msg.value}(token0, amount0, amount0 * 99/100 , msg.value*99/100, address(this), block.timestamp);

    checkSetApprove(lpToken, address(lp), liquidity);
    lp.deposit(lpToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), lpToken, liquidity);
    
    cleanup(token0);
    cleanupEth();
  }
  

  
  /// @notice Add liquidity to a Uniswap pool then add the LP tokens to the ROE pool
  /// @param poolId Id of the ROE pool
  /// @param token0 Underlying token for lpToken
  /// @param amount0 Amount of token0 to add to the AMM pool
  /// @param token1 Underlying token for lpToken
  /// @param amount1 Mininmum amount of token1 added to the pool
  /// @return amountA Amount of token added
  /// @return amountB Amount of token added
  /// @return liquidity LP amount created
  /// @dev Slippage is unpredictable, amount1 is the amountTokenMin value that should be received when swapExactTokensForTokens token0 to token1
  function zapInSingleAsset(uint poolId, address token0, uint amount0, address token1, uint amount1) 
    external 
    nonReentrant()
    returns (uint amountA, uint amountB, uint liquidity)
  {
    require(amount0 > 0, "ZB: Zero Amount");
    (ILendingPool lp, IUniswapV2Router01 router,) = getPoolAddresses(poolId);
    address lpToken = IUniswapV2Factory(router.factory()).getPair(token0, token1);
    ERC20(token0).safeTransferFrom(msg.sender, address(this), amount0);
    uint[] memory swapped;
    // localization
    {
      address[] memory path = new address[](2);
      path[0] = token0; path[1] = token1; 
      
      checkSetApprove(token0, address(router), amount0);
      swapped = router.swapExactTokensForTokens(
          getSwapAmt(lpToken, token0, amount0),
          amount1,
          path,
          address(this),
          block.timestamp
        );
      checkSetApprove(token1, address(router), swapped[1]);
    }
    amount0 = amount0 - swapped[0];
    uint limit = amount0 * 99 / 100;
    (amountA, amountB, liquidity) = router.addLiquidity(token0, token1, amount0, swapped[1], limit, amount1, address(this), block.timestamp);

    checkSetApprove(lpToken, address(lp), liquidity);
    lp.deposit(lpToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), lpToken, liquidity);

    cleanup(token0);
    cleanup(token1);
  }
  

  /// @notice Add liquidity using ETH to a Uniswap pool then add the LP tokens to the ROE pool
  /// @param poolId Id of the ROE pool
  /// @param token0 Underlying token for lpToken
  /// @param amount0 Mininmum amount of token0 added to the pool
  /// @return amountToken Amount of token added
  /// @return amountEth amount of ETH added
  /// @return liquidity LP amount created
  /// @dev Slippage is unpredictable, amount0 is the amountTokenMin value that should be received when swapExactTokensForTokens token0 to token1
  function zapInSingleAssetETH(uint poolId, address token0, uint amount0)
    external payable 
    nonReentrant()
    returns (uint amountToken, uint amountEth, uint liquidity)
  {
    require(msg.value > 0, "ZB: Zero Amount");
    (ILendingPool lp, IUniswapV2Router01 router,) = getPoolAddresses(poolId);
    address lpToken = IUniswapV2Factory(router.factory()).getPair(router.WETH(), token0);
    
    address[] memory path = new address[](2);
    path[0] = router.WETH(); path[1] = token0; 
    uint[] memory swapped = router.swapExactETHForTokens{value: getSwapAmt(lpToken, router.WETH(), msg.value)}(
        amount0,
        path,
        address(this),
        block.timestamp
      );
    checkSetApprove(token0, address(router), swapped[1]);
    (amountToken, amountEth, liquidity) = router.addLiquidityETH{value: msg.value - swapped[0]}(token0, swapped[1], (msg.value - swapped[0])*99/100, amount0, address(this), block.timestamp);

    checkSetApprove(lpToken, address(lp), liquidity);
    lp.deposit(lpToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), lpToken, liquidity);

    cleanup(token0);
    cleanupEth();
  }
  

  /// @notice Removes liquidity from ROE then remove from Uniswap then send back to user
  /// @param poolId Id of the ROE pool
  /// @param token LP token 
  /// @param amount Amount to withdraw
  /// @return amount0 Amount of token0 removed
  /// @return amount1 Amount of token1 removed
  function zapOut(uint poolId, address token, uint amount)
    public nonReentrant()
    returns(uint amount0, uint amount1)
  {
    address token0 = IUniswapV2Pair(token).token0();
    address token1 = IUniswapV2Pair(token).token1();
    
    (ILendingPool lp, IUniswapV2Router01 router, IPriceOracle oracle) = getPoolAddresses(poolId);
    if (amount == 0 ) amount = ERC20( lp.getReserveData(token).aTokenAddress ).balanceOf(msg.sender);
    // Transfer LP tokens here
    ERC20( lp.getReserveData(token).aTokenAddress ).safeTransferFrom(msg.sender, address(this) , amount);
    lp.withdraw(token, amount, address(this));
    
    // Withdraw underlying from AMM
    if ( ERC20(token).allowance(address(this), address(router)) < amount ) ERC20(token).safeIncreaseAllowance(address(router), type(uint256).max);
    (amount0, amount1) = router.removeLiquidity(
      token0,
      token1,
      amount,
      1,
      1,
      msg.sender,
      block.timestamp
    );
    
    validateValuesAgainstOracle(oracle, token0, amount0, token1, amount1);
    emit ZapOut(address(lp), token, amount);
  }
  
  /// @notice Removes liquidity from ROE/Uniswap using EIP2612 permit to allow offchain approval for the ROE token
  /// @param poolId Id of the ROE pool
  /// @param token LP token 
  /// @param amount Amount to withdraw
  /// @param permit EIP2612 permit
  function zapOutWithPermit(uint poolId, address token, uint amount, PermitParam calldata permit) external 
    returns(uint amount0, uint amount1)
  {
    (ILendingPool lp,,) = getPoolAddresses(poolId);
    address roeToken = lp.getReserveData(token).aTokenAddress;
    ERC2612(roeToken).permit(msg.sender, address(this), permit.value, permit.deadline, permit.v, permit.r, permit.s);
    
    (amount0, amount1) = zapOut(poolId, token, amount);
  }

  
  ///////// VARIOUS
  
  receive() external payable {}
 

  function cleanupEth() internal {
    if ( address(this).balance > 0 ) payable(msg.sender).transfer(address(this).balance);
  }

 
  /// @notice Send back full balance of token to sender
  /// @param token Address of the token
  function cleanup(address token) private {
    uint bal = ERC20(token).balanceOf(address(this));
    if ( bal > 0 ) ERC20(token).safeTransfer(msg.sender, bal);
  }
  
  /// @notice Helper that checks current allowance and approves if necessary
  /// @param token Target token
  /// @param spender Spender
  /// @param amount Amount below which we need to approve the token spending
  function checkSetApprove(address token, address spender, uint amount) private {
    if ( ERC20(token).allowance(address(this), spender) < amount ) ERC20(token).safeIncreaseAllowance(spender, type(uint256).max);
  }

  
  /*
    For single-sided Uniswap V2 addition 
    - https://blog.alphaventuredao.io/onesideduniswap/
    - Hard-coded for 0.3% fees
    - Maximum rounding error = 2, due to two floor operations when processed in integer evm.
  */
  /// @notice Calculate optimal liquidity for a swap
  /// @param lpToken LP token
  /// @param assetA underlying token A
  /// @param amtA Available amount of token A
  /// @return amount Target liquidity amount
  function getSwapAmt(address lpToken, address assetA, uint256 amtA) internal view returns (uint256 amount) {
    (uint res0, uint res1,) = IUniswapV2Pair(lpToken).getReserves();
    uint resA = assetA == IUniswapV2Pair(lpToken).token0() ? res0 : res1;
    amount = (sqrt(resA * (3988000 * amtA + 3988009 * resA)) - resA * 1997) / 1994; 
  }
  
  /// @notice Babylonian method for sqrt
  /// @param x sqrt parameter
  /// @return y Square root
  function sqrt(uint x) internal pure returns (uint y) {
      uint z = (x + 1) / 2;
      y = x;
      while (z < y) {
          y = z;
          z = (x / z + z) / 2;
      }
  }
  

  /// @notice Get lp and router from RoeRouter
  /// @param poolId Id of the ROE pool
  /// @return lp Lending pool address
  function getPoolAddresses(uint poolId) private view returns (ILendingPool lp, IUniswapV2Router01 router, IPriceOracle oracle) {
    (address lpap,,, address r, ) = ROEROUTER.pools(poolId);
    lp = ILendingPool(ILendingPoolAddressesProvider(lpap).getLendingPool());
    oracle = IPriceOracle(ILendingPoolAddressesProvider(lpap).getPriceOracle());
    router = IUniswapV2Router01(r);
  }


  /// @notice Check LP underlying assets value against oracle values: allow a 1% error
  /// @param oracle The Lending pool oracle for the LP token
  /// @param assetA The first token address
  /// @param amountA The first token amount
  /// @param assetB The second token address
  /// @param amountB The second token amount
  function validateValuesAgainstOracle(IPriceOracle oracle, address assetA, uint amountA, address assetB, uint amountB) internal view {
    uint decimalsA = ERC20(assetA).decimals();
    uint decimalsB = ERC20(assetB).decimals();
    uint valueA = amountA * oracle.getAssetPrice(assetA);
    uint valueB = amountB * oracle.getAssetPrice(assetB);
    if (decimalsA > decimalsB) valueA = valueA / 10 ** (decimalsA - decimalsB);
    else if (decimalsA < decimalsB) valueB = valueB / 10 ** (decimalsB - decimalsA);
    require( valueA <= valueB * 101 / 100, "ZB: LP Oracle Error");
    require( valueB <= valueA * 101 / 100, "ZB: LP Oracle Error");
  }
  
}