
# Good Entry

Collection of solidity contracts for structured products focusing on unlocking optionality from AMM-LP tokens on EVM chains.

## Code 

### V1
Files here are asset bearing
|File           | Description  |
|--|--|
| TokenisableRange.sol |  Holds UniV3 NFTs and tokenises the ranges
| RangeManager.sol | Assists with creation and tracking of V3 TokenisableRanges, and helping user enter and exit these ranges through the Lending Pool |
| RoeRouter.sol | Whitelists GE pools |
| GeVault.sol | Holds single tick Tokenisable Ranges |

### Position Managers
Handle leverage borrowing + repayments, have priviledge access to the Lending pools
|File           | Description  |
|--|--|
| PositionManager.sol  | Basic reusable functions |
| LonggPositionManager.sol  | Leverage/deleverage tool for LP tokens and positions + risk management/liquidation tool, non asset bearing  |
| OptionsPositionManager.sol | Leverage/deleverage tool for Tokenized Ranges + risk management/liquidation tool, non asset bearing  |
| RangePositionManager.sol | Leverage/deleverage tool for Tokenized Ranges farming, non asset bearing |


### Helper / Aux
Files here interact with asset bearing contracts, but themselves do not hold state nor assets
|File           | Description  |
|--|--|
|LPOracle.sol | Oracle for LP token, given 2 Chainlink feeds |
|OracleConvert.sol | Contract takes 2 Chainlink feeds, and synthesises a composite price (E.g. Given TRIBE / ETH and ETH / USD, return TRIBE / USD)
| ZapBox.sol | Helpers to assist users to convert 1 or 2 assets into LP positions |
| ZapBoxTR.sol | Helpers to assist users to convert 1 or 2 assets into TR positions |
|openzeppelin-solidity/* | Open-Zeppelin contracts, version 4.4.1 |
|lib/* | Uniswap V3 helper libraries |



## Testing

### Brownie

The project uses Brownie as a testing framework. https://eth-brownie.readthedocs.io/en/stable/index.html

|File| Unit Tests For | Details |
|--|--|--|
| test_RoeRouter.py | RoeRouter.sol |
| test_ranger.py | TokenisableRange.sol, RangeManager.sol |
| test_ranger_WBTCUSDC.py | TokenisableRange.sol |
| test_PositionManager.py | PositionManager/PositionManager.sol |
| test_OptionsPositionManager.py | PositionManager/OptionsPositionManager.sol |
| test_LonggPositionManager.py | PositionManager/LonggPositionManager.sol |
| test_RangeManager.py, test_RangeManager_WBTCUSDC | RangeManager.sol |
| test_zap.py | helpers/ZapBox.sol |
| test_zapTR.py | helpers/ZapBoxTR.sol |
| test_GeVault.py | GeVault.sol |
| test_GeVault_arbi.py | GeVault.sol | Specific test to run on Arbitrum network |


First, start a local mainnet-fork - this is needed as we are testing Chainlink feeds. You can use Alchemy or Infura or any archive node.

```bash
ganache-cli --port 8545 --gasLimit 12000000 --accounts 10 --hardfork istanbul --mnemonic brownie --fork https://eth-mainnet.g.alchemy.com/v2/aE_kYsizNYWhqZ18ryeMsl-JkWmCMgFj@16360000 --host 0.0.0.0
```

Then, run the tests,

```bash
brownie test
```

should return something like

```
pinni@Pinni0-VM0:~/thetanuts/longG$ brownie test tests/test_vault.py --network matic-main-fork -I
Brownie v1.17.2 - Python development framework for Ethereum

=========================================================================================================== test session starts ============================================================================================================
platform linux -- Python 3.8.10, pytest-6.2.5, py-1.11.0, pluggy-1.0.0
rootdir: /home/pinni/thetanuts/longG
plugins: eth-brownie-1.17.2, forked-1.3.0, web3-5.25.0, xdist-1.34.0, hypothesis-6.27.3, requests-mock-1.6.0
collected 11 items
Attached to local RPC client listening at '127.0.0.1:8546'...

tests/test_vault.py ...........                                                                                                                                                                                                      [100%]

============================================================================================================= warnings summary =============================================================================================================
../../.local/lib/python3.8/site-packages/brownie/network/main.py:44
  /home/pinni/.local/lib/python3.8/site-packages/brownie/network/main.py:44: BrownieEnvironmentWarning: Development network has a block height of 27595258
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/warnings.html
================================================================================================ 11 passed, 1 warning in 104.87s (0:01:44) =================================================================================================
```
For latest coverage and testing report, please refer to the reports/folder 
 - coverage.json - Can be used with Brownie GUI
 - coverage.html - As Brownie GUI may be unreliable, a HTML report is generated for viewing
 - coverage_cli.txt - Screen dump from running full test suite in coverage mode; shows coverage statistics

#### Coverage 

Current coverage
```
=================================================================================================== Coverage ===================================================================================================
contract: GeVault - 57.5%
    GeVault.checkSetApprove - 100.0%
    GeVault.getAdjustedBaseFee - 100.0%
    GeVault.deployAssets - 81.2%
    Address.functionCallWithValue - 75.0%
    ERC20._burn - 75.0%
    ERC20._mint - 75.0%
    GeVault.depositAndStash - 75.0%
    GeVault.getActiveTickIndex - 75.0%
    GeVault.rebalance - 75.0%
    SafeERC20._callOptionalReturn - 75.0%
    GeVault.removeFromTick - 70.8%
    GeVault.deposit - 67.9%
    GeVault.withdraw - 67.3%
    GeVault.poolMatchesOracle - 58.3%
    Address.verifyCallResult - 37.5%
    GeVault.<receive> - 25.0%
    ERC20._approve - 0.0%
    ERC20._transfer - 0.0%
    ERC20.decreaseAllowance - 0.0%
    ERC20.transferFrom - 0.0%
    GeVault.latestAnswer - 0.0%
    Ownable.transferOwnership - 0.0%

  contract: LonggPositionManager - 87.3%
    LonggPositionManager.executeOperation - 100.0%
    LonggPositionManager.executeOperationLeverage - 100.0%
    LonggPositionManager.openOneSidedPosition - 100.0%
    LonggPositionManager.rebalanceTokens - 100.0%
    LonggPositionManager.softLiquidateLP - 100.0%
    LonggPositionManager.swapAllTokens - 100.0%
    LonggPositionManager.swapExactly - 100.0%
    PositionManager.PMWithdraw - 100.0%
    PositionManager.checkSetAllowance - 100.0%
    LonggPositionManager.clos - 97.9%
    LonggPositionManager.deltaNeutralize - 87.5%
    LonggPositionManager.executeOperationLiquidate - 87.5%
    LonggPositionManager.softLiquidate - 87.5%
    Address.functionCallWithValue - 75.0%
    LonggPositionManager._calculateDebt - 75.0%
    LonggPositionManager.getTargetAmountFromOracle - 75.0%
    PositionManager.validateValuesAgainstOracle - 75.0%
    SafeERC20._callOptionalReturn - 75.0%
    PositionManager.cleanup - 45.0%
    Address.verifyCallResult - 37.5%

  contract: NullOracle - 100.0%
    NullOracle.getAssetPrice - 100.0%

  contract: OptionsPositionManager - 82.7%
    OptionsPositionManager.buyOptions - 100.0%
    OptionsPositionManager.calculateAndSendFee - 100.0%
    OptionsPositionManager.executeBuyOptions - 100.0%
    OptionsPositionManager.executeLiquidation - 100.0%
    OptionsPositionManager.executeOperation - 100.0%
    OptionsPositionManager.sellOptions - 100.0%
    PositionManager.PMWithdraw - 100.0%
    PositionManager.checkSetAllowance - 100.0%
    OptionsPositionManager.withdrawOptionAssets - 96.4%
    OptionsPositionManager.closeDebt - 87.9%
    OptionsPositionManager.close - 83.3%
    Address.functionCallWithValue - 75.0%
    OptionsPositionManager.checkExpectedBalances - 75.0%
    OptionsPositionManager.getTargetAmountFromOracle - 75.0%
    OptionsPositionManager.liquidate - 75.0%
    OptionsPositionManager.swapTokensForExactTokens - 75.0%
    OptionsPositionManager.withdrawOptions - 75.0%
    SafeERC20._callOptionalReturn - 75.0%
    PositionManager.cleanup - 50.0%
    Address.verifyCallResult - 37.5%

  contract: RangeManager - 88.6%
    RangeManager.generateRange - 100.0%
    RangeManager.transferAssetsIntoStep - 100.0%
    RangeManager.removeFromStep - 93.8%
    RangeManager.checkNewRange - 91.7%
    RangeManager.cleanup - 91.7%
    Ownable.transferOwnership - 0.0%

  contract: RangerPositionManager - 37.4%
    RangerPositionManager.farmRange - 100.0%
    PositionManager.checkSetAllowance - 75.0%
    RangerPositionManager.execute - 68.8%
    PositionManager.cleanup - 41.7%
    PositionManager.PMWithdraw - 0.0%
    PositionManager.validateValuesAgainstOracle - 0.0%
    RangerPositionManager.closeRange - 0.0%

  contract: Test_LonggPositionManager - 9.6%
    LonggPositionManager.getTargetAmountFromOracle - 100.0%
    PositionManager.validateValuesAgainstOracle - 93.8%
    LonggPositionManager._calculateDebt - 0.0%
    LonggPositionManager.clos - 0.0%
    LonggPositionManager.deltaNeutralize - 0.0%
    LonggPositionManager.executeOperation - 0.0%
    LonggPositionManager.executeOperationLeverage - 0.0%
    LonggPositionManager.executeOperationLiquidate - 0.0%
    LonggPositionManager.openOneSidedPosition - 0.0%
    LonggPositionManager.rebalanceTokens - 0.0%
    LonggPositionManager.softLiquidate - 0.0%
    LonggPositionManager.softLiquidateLP - 0.0%
    LonggPositionManager.swapAllTokens - 0.0%
    LonggPositionManager.swapExactly - 0.0%
    PositionManager.PMWithdraw - 0.0%
    PositionManager.checkSetAllowance - 0.0%
    PositionManager.cleanup - 0.0%

  contract: Test_OptionsPositionManager - 12.6%
    OptionsPositionManager.getTargetAmountFromOracle - 100.0%
    OptionsPositionManager.swapTokensForExactTokens - 91.7%
    PositionManager.checkSetAllowance - 75.0%
    OptionsPositionManager.buyOptions - 0.0%
    OptionsPositionManager.calculateAndSendFee - 0.0%
    OptionsPositionManager.checkExpectedBalances - 0.0%
    OptionsPositionManager.close - 0.0%
    OptionsPositionManager.closeDebt - 0.0%
    OptionsPositionManager.executeBuyOptions - 0.0%
    OptionsPositionManager.executeLiquidation - 0.0%
    OptionsPositionManager.executeOperation - 0.0%
    OptionsPositionManager.liquidate - 0.0%
    OptionsPositionManager.sellOptions - 0.0%
    OptionsPositionManager.withdrawOptionAssets - 0.0%
    OptionsPositionManager.withdrawOptions - 0.0%
    PositionManager.PMWithdraw - 0.0%
    PositionManager.cleanup - 0.0%

  contract: Test_ZapBox - 3.3%
    ZapBox.cleanupEth - 75.0%
    ZapBox.checkSetApprove - 0.0%
    ZapBox.cleanup - 0.0%
    ZapBox.getSwapAmt - 0.0%
    ZapBox.zapIn - 0.0%
    ZapBox.zapInETH - 0.0%
    ZapBox.zapInSingleAsset - 0.0%
    ZapBox.zapOut - 0.0%

  contract: TickMath - 86.5%
    TickMath.getSqrtRatioAtTick - 89.2%
    TickMath.getTickAtSqrtRatio - 72.5%

  contract: TokenisableRange - 67.0%
    ERC20.transferFrom - 100.0%
    TokenisableRange.init - 100.0%
    TokenisableRange.initProxy - 100.0%
    ERC20._approve - 87.5%
    ERC20._burn - 87.5%
    TokenisableRange.returnExpectedBalance - 87.5%
    ERC20._transfer - 83.3%
    LiquidityAmounts.getAmountsForLiquidity - 81.7%
    ERC20._mint - 75.0%
    LiquidityAmounts.getAmount0ForLiquidity - 50.0%
    LiquidityAmounts.getAmount1ForLiquidity - 50.0%
    TokenisableRange.getValuePerLPAtPrice - 50.0%
    TokenisableRange.withdraw - 50.0%
    TokenisableRange.deposit - 49.6%
    FullMath.mulDiv - 25.8%
    ERC20.decreaseAllowance - 0.0%

  contract: UpgradeableBeacon - 100.0%
    Ownable.transferOwnership - 100.0%

  contract: ZapBox - 95.8%
    ZapBox.checkSetApprove - 100.0%
    ZapBox.cleanup - 100.0%
    ZapBox.getSwapAmt - 100.0%
    ZapBox.zapIn - 100.0%
    ZapBox.zapInSingleAsset - 100.0%
    ZapBox.zapOut - 100.0%
    ZapBox.zapInETH - 91.7%
    ZapBox.cleanupEth - 75.0%

  contract: ZapBoxTR - 85.7%
    ZapBoxTR.cleanup - 100.0%
    ZapBoxTR.cleanupEth - 100.0%
    ZapBoxTR.zapOut - 91.7%
    ZapBoxTR.zapIn - 87.5%
    ZapBoxTR.zapInETH - 79.2%
    ZapBoxTR.checkSetApprove - 75.0%
```

### Hardhat

The Hardhat tests are in the directory ```test``` and can be runned with ```npx hardhat test```

Coverage can tested with ```npx hardhat coverage  --network localhost```

## Hardhat Console

To get console.log when dev, ```import "../../node_modules/hardhat/console.sol";```

Install hardhat and related node packages with ```yarn install```

Instead of running ganache-cli, use ```npx hardhat node --network hardhat```.

The hardhat-config.js file uses my Alchemy endpoint, that can be changed, this is the network > hardhat config.
