// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;

import "../openzeppelin-solidity/contracts/token/ERC20/IERC20.sol";
import "../GeVault.sol";


/// @notice Migrate liquidity from a vault to another vault
contract MigrateVault {
  address private immutable WETH;


  constructor(address weth){
    WETH = weth;
  }


  receive() external payable {}


  /// @notice Migrate liquidity from an older vault
  function migrate(uint amount, address token, address payable sourceVault, address payable targetVault) public payable returns (uint liquidity){
    if(amount == 0) amount = IERC20(sourceVault).balanceOf(msg.sender);
    IERC20(sourceVault).transferFrom(msg.sender, address(this), amount);
    GeVault(sourceVault).withdraw(amount, token);
    uint tAmount = IERC20(token).balanceOf(address(this));
    IERC20(token).approve(targetVault, tAmount);
    if (address(this).balance > 0 && token == WETH )
      liquidity = GeVault(targetVault).deposit{value: address(this).balance}(token, 0);
    else
      liquidity = GeVault(targetVault).deposit(token, tAmount);
    GeVault(targetVault).transfer(msg.sender, liquidity);
  }
}