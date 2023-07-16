// SPDX-License-Identifier: MIT

pragma solidity >=0.6.2;

interface ILendingPoolV1 {
    function deposit(
        address _reserve,
        uint256 _amount,
        uint16 _referralCode
    ) external payable;
}
