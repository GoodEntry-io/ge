// SPDX-License-Identifier: none
pragma solidity 0.8.19;

import "../openzeppelin-solidity/contracts/token/ERC20/ERC20.sol";
import "../openzeppelin-solidity/contracts/token/ERC20/utils/SafeERC20.sol";
import "../openzeppelin-solidity/contracts/security/ReentrancyGuard.sol";
import "../../interfaces/IWETH.sol";
import {ILendingPool} from "../../interfaces/IAaveLendingPoolV2.sol";
import {IPriceOracle} from "../../interfaces/IPriceOracle.sol";
import {ILendingPoolAddressesProvider} from "../../interfaces/ILendingPoolAddressesProvider.sol";
import "../RoeRouter.sol";
import "../TokenisableRange.sol";

interface ERC2612 {
  function permit(address owner, address spender, uint256 value, uint256 deadline, uint8 v, bytes32 r, bytes32 s) external;
}


contract ZapBoxTR is ReentrancyGuard {
  using SafeERC20 for ERC20;
  RoeRouter public ROEROUTER; // set to immutable after coverage tests are done
  IWETH public WETH;
  
  
  /// EVENTS
  event ZapIn(address lendingPool, address trToken, uint amount);
  event ZapOut(address lendingPool, address trToken, uint amount);
  

  constructor(address roeRouter, address weth) {
    require(roeRouter != address(0x0) && weth != address(0x0), "ZB: Invalid Address");
    ROEROUTER = RoeRouter(roeRouter);
    WETH = IWETH(weth);
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
  /// @param amount0 Amount of token0 to add to the AMM pool
  /// @param amount1 Amount of token1 to add to the AMM pool
  /// @return amountA Amount of token added
  /// @return amountB Amount of token added
  /// @return liquidity LP amount created
  /// @dev Slippage is fixed and set to 1% (min amount of each token added 99%) to prevent sandwiching
  function zapIn(uint poolId, address trToken, uint amount0, uint amount1) 
    external
    nonReentrant()
    returns (uint amountA, uint amountB, uint liquidity)
  {
    (ILendingPool lp, address token0, address token1, ) = getPoolAddresses(poolId);
    if (amount0 > 0 ){
      ERC20(token0).safeTransferFrom(msg.sender, address(this), amount0);
      checkSetApprove(token0, trToken, amount0);
    }
    if (amount1 > 0 ) {
      ERC20(token1).safeTransferFrom(msg.sender, address(this), amount1);
      checkSetApprove(token1, trToken, amount1);
    }
    liquidity = TokenisableRange(trToken).deposit(amount0, amount1);
    
    checkSetApprove(trToken, address(lp), liquidity);
    lp.deposit(trToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), trToken, liquidity);
    
    amountA = amount0 - cleanup(token0);
    amountB = amount1 - cleanup(token1);
  }


  /// @notice Add liquidity using ETH to a Uniswap pool then add the LP tokens to the ROE pool
  /// @param poolId Id of the ROE pool
  /// @param token Underlying token for lpToken
  /// @param amount Amount of token0 to add to the AMM pool
  /// @return amountToken Amount of token added
  /// @return amountEth amount of ETH added
  /// @return liquidity LP amount created
  /// @dev Slippage is fixed and set to 1% (min amount of each token added 99%) to prevent sandwiching
  function zapInETH(uint poolId, address trToken, address token, uint amount) 
    external payable 
    nonReentrant()
    returns (uint amountToken, uint amountEth, uint liquidity)
  {
    (ILendingPool lp, address token0, address token1, ) = getPoolAddresses(poolId);
    require(address(token0) == address(WETH) || address(token1) == address(WETH), "ZB: Not ETH Pair" );
    require(token == token0 || token == token1, "ZB: Invalid Token");
    
    if ( amount > 0) {
      ERC20(token).safeTransferFrom(msg.sender, address(this), amount);
      checkSetApprove(token, trToken, amount);
    }
    if (msg.value > 0){
      // wraps ETH by sending to the wrapper that sends back WETH
      WETH.deposit{value: msg.value}();
      checkSetApprove(address(WETH), trToken, msg.value);
    }
    
    liquidity = TokenisableRange(trToken).deposit(
      token == address(token0) ? amount : msg.value,
      token == address(token0) ? msg.value : amount
    );

    checkSetApprove(trToken, address(lp), liquidity);
    lp.deposit(trToken, liquidity, msg.sender, 0);
    emit ZapIn(address(lp), trToken, liquidity);
    
    amountToken = amount - cleanup(token);
    amountEth = msg.value - cleanupEth();
  }
  

  /// @notice Removes liquidity from ROE then remove from Uniswap then send back to user
  /// @param poolId Id of the ROE pool
  /// @param trToken LP token 
  /// @param amount Amount to withdraw
  /// @return amount0 Amount of token0 removed
  /// @return amount1 Amount of token1 removed
  function zapOut(uint poolId, address trToken, uint amount, bool wethAsEth)
    public nonReentrant()
    returns(uint amount0, uint amount1)
  {
    (ILendingPool lp, address token0, address token1, IPriceOracle oracle) = getPoolAddresses(poolId);
    if (amount == 0 ) amount = ERC20( lp.getReserveData(trToken).aTokenAddress ).balanceOf(msg.sender);
    // Transfer LP tokens here
    ERC20( lp.getReserveData(trToken).aTokenAddress ).safeTransferFrom(msg.sender, address(this) , amount);
    lp.withdraw(trToken, amount, address(this));
    
    // Withdraw underlying from AMM
    (amount0, amount1) = TokenisableRange(trToken).withdraw(amount, 0, 0);
 
    // Require valueOut >= 98% theoretical value to avoid sandwich
    require(
        amount0 * oracle.getAssetPrice(token0) / 10**ERC20(token0).decimals()
        + amount1 * oracle.getAssetPrice(token1) / 10**ERC20(token1).decimals()
        >= TokenisableRange(trToken).latestAnswer() * amount / 1e18 * 98 / 100,
        "ZB: Slippage"
      );
    
    if (wethAsEth){
      WETH.withdraw(WETH.balanceOf(address(this)));
      cleanupEth();
    }
    cleanup(token0);
    cleanup(token1);
    
    emit ZapOut(address(lp), trToken, amount);
  }
  
  
  /// @notice Removes liquidity from ROE/Uniswap using EIP2612 permit to allow offchain approval for the ROE token
  /// @param poolId Id of the ROE pool
  /// @param token TR token 
  /// @param amount Amount to withdraw
  /// @param permit EIP2612 permit
  function zapOutWithPermit(uint poolId, address token, uint amount, bool wethAsEth, PermitParam calldata permit) external 
    returns(uint amount0, uint amount1)
  {
    (ILendingPool lp,,, ) = getPoolAddresses(poolId);
    address roeToken = lp.getReserveData(token).aTokenAddress;
    ERC2612(roeToken).permit(msg.sender, address(this), permit.value, permit.deadline, permit.v, permit.r, permit.s);
    
    (amount0, amount1) = zapOut(poolId, token, amount, wethAsEth);
  }

  
  ///////// VARIOUS
  
  receive() external payable {}
 

  function cleanupEth() internal returns (uint bal) {
    bal = address(this).balance;
    if ( bal > 0 ) payable(msg.sender).transfer(bal);
  }

 
  /// @notice Send back full balance of token to sender
  /// @param token Address of the token
  function cleanup(address token) private returns (uint bal )  {
    bal = ERC20(token).balanceOf(address(this));
    if ( bal > 0 ) ERC20(token).safeTransfer(msg.sender, bal);
  }
  
  /// @notice Helper that checks current allowance and approves if necessary
  /// @param token Target token
  /// @param spender Spender
  /// @param amount Amount below which we need to approve the token spending
  function checkSetApprove(address token, address spender, uint amount) private {
    if ( ERC20(token).allowance(address(this), spender) < amount ) ERC20(token).safeIncreaseAllowance(spender, type(uint256).max);
  }


  /// @notice Get lp and router from RoeRouter
  /// @param poolId Id of the ROE pool
  /// @return lp Lending pool address
  function getPoolAddresses(uint poolId) private view returns (ILendingPool lp, address token0, address token1, IPriceOracle oracle) {
    (address lpap, address _token0, address _token1,, ) = ROEROUTER.pools(poolId);
    token0 = _token0;
    token1 = _token1;
    lp = ILendingPool(ILendingPoolAddressesProvider(lpap).getLendingPool());
    oracle = IPriceOracle(ILendingPoolAddressesProvider(lpap).getPriceOracle());
  }
}