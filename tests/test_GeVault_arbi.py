import pytest, brownie
from brownie import network
import math


# CONSTANTS
USDC = "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"
WETH = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
TREASURY="0x50101017adf9D2d06C395471Bc3D6348589c3b97" # random empty
ROUTER="0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
ROUTERV3="0xE592427A0AEce92De3Edee1F18E0157C05861564"
UNISWAPPOOLV3 = "0xc31e54c7a869b9fcbecc14363cf510d1c41fa443" # ETH univ3 ETH-USDC 0.05%
# LPAD for btc 0xe7f6F6Cd1Be8313a05e0E38bA97B2A5Dfed7616d - for weth "0x01b76559D512Fa28aCc03630E8954405BcBB1E02"
LENDING_POOL_ADDRESSES_PROVIDER = "0x067350E557BCeAeb08806Aacd4AecB701c881c67" 
AAVE_WETH = "0xe50fa9b3c56ffb159cb0fca61f5c9d750e8128c8"
AAVE_USDC = "0x625e7708f30ca75bfd92586e17077590c60eb4cd"
NULL = "0x0000000000000000000000000000000000000000"

TICKS = [1500, 1600, 1700, 1800, 1900, 2000]

@pytest.fixture(scope="module", autouse=True)
def weth(interface, accounts):
  # Claim WETH from MATIC-Aave pool
  aaveWETH = accounts.at("0x28424507fefb6f7f8e9d3860f56504e4e5f5f390", force=True)
  weth = interface.IWETH(WETH, owner=aaveWETH)
  yield weth

@pytest.fixture(scope="module", autouse=True)
def usdc(interface, accounts):
  # Claim USDC from Stargate stake account
  stargate = accounts.at("0x1205f31718499dBf1fCa446663B532Ef87481fe1", force=True)
  usdc  = interface.ERC20(USDC, owner=stargate)
  yield usdc
  
@pytest.fixture(scope="module", autouse=True)
def routerV3(interface):
  routerV3 = interface.ISwapRouter(ROUTERV3)
  yield routerV3
  
@pytest.fixture(scope="module", autouse=True)
def roerouter(RoeRouter, owner):
  roerouter = RoeRouter.deploy(TREASURY, {"from": owner})
  roerouter.addPool(LENDING_POOL_ADDRESSES_PROVIDER, WETH, USDC, ROUTER, {"from": owner})
  yield roerouter

# No isolation when testing uniswap as it will cause reentrancy reverts
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass

@pytest.fixture(scope="module", autouse=True)
def pm(OptionsPositionManager, owner, roerouter):
  pm = OptionsPositionManager.deploy(roerouter, {"from": owner})
  yield pm
  
@pytest.fixture(scope="module", autouse=True)
def lendingPool(interface, accounts):
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  try:
    lpadd.setLendingPoolImpl("0x09add1BC0CaC5FD269CE5eceA034e218bF16FA76", {"from": poolAdmin}) # Set to correct implementation
  except: 
    pass
  configurator = interface.ILendingPoolConfigurator(lpadd.getLendingPoolConfigurator());
  lendingPool = interface.ILendingPool(lpadd.getLendingPool())
  lendingPool.setSoftLiquidationThreshold(102e16, {"from": poolAdmin})
  yield lendingPool
    
@pytest.fixture(scope="module", autouse=True)
def oracle(interface, accounts):
  lpAdd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  oracle = interface.IAaveOracle( lpAdd.getPriceOracle() )
  yield oracle


@pytest.fixture(scope="module", autouse=True)
def config(interface, accounts):
  lpAdd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  config = interface.ILendingPoolConfigurator(lpAdd.getLendingPoolConfigurator() )
  yield config
  
  
# Call to seed accounts before isolation tests
@pytest.fixture(scope="module", autouse=True)
def seed_accounts( weth, usdc, user, owner, lendingPool, accounts):
  try: 
    aaveUSDC = accounts.at(AAVE_USDC, force=True)
    aaveWETH = accounts.at(AAVE_WETH, force=True)
    
    weth.approve(lendingPool, 2**256-1, {"from": aaveWETH})
    weth.transfer(owner, 10e18, {"from": aaveWETH})
    lendingPool.deposit(weth, 10e18, owner, 0, {"from": aaveWETH}) 
    #lendingPool.deposit(weth, 30e18, user, 0, {"from": lotsTokens}) 

    usdc.approve(lendingPool, 2**256-1, {"from": aaveUSDC})
    usdc.transfer(owner, 5e10, {"from": aaveUSDC})
    usdc.transfer(user, 5e10, {"from": aaveUSDC})
    lendingPool.deposit(usdc, 10e10, owner, 0, {"from": aaveUSDC}) 
    lendingPool.deposit(usdc, 1e10, user, 0, {"from": aaveUSDC}) 

  except Exception as e:
    print(e)

  
@pytest.fixture(scope="module", autouse=True)
def contracts(owner, Strings, TickMath, TokenisableRange, UpgradeableBeacon, RangeManager, lendingPool, weth, usdc):
  Strings.deploy({"from": owner})
  TickMath.deploy({"from": owner})
  tr = TokenisableRange.deploy({"from": owner})
  trb = UpgradeableBeacon.deploy(tr, {"from": owner})
  r = RangeManager.deploy(lendingPool, usdc, weth, {"from": owner})
  yield tr, trb, r
  
@pytest.fixture(scope="module", autouse=True)
def gevault(accounts, chain, pm, owner, timelock, lendingPool, GeVault, roerouter):
  gevault = GeVault.deploy(TREASURY, roerouter, UNISWAPPOOLV3, 0, "GeVault WETHUSDC", "GEV-ETHUSDC", WETH, True, {"from": owner})
  gevault.pushTick("0x9D6B29EC56492BE7422ae77C336698DAE73f9781", {"from": owner}) # 1600
  gevault.pushTick("0xA650326776e85F96Ef67249fC9AfcC7c8e8d7424", {"from": owner}) # 1700
  gevault.pushTick("0x5c09C0194FC89CcDAe753f348D1534108F29e90a", {"from": owner}) # 1800
  gevault.pushTick("0x503b1d37CbF6AdEc32c6a2a5542848B5953F6CD8", {"from": owner}) # 1900
  gevault.pushTick("0x84A87d273107db6301d6c5d6667a374ff05427bB", {"from": owner}) # 2000
  yield gevault
  

# Check if 2 values are within 1%
def nearlyEqual(value0, value1):
  if (value1 == 0): return value1 == value0
  else: return abs (value0-value1) / value1 < 0.01


@pytest.mark.skip_coverage
def exactSwap(routerV3, params, extra): # pragma: no cover
  return routerV3.exactInputSingle(params, extra)


# Deploy contract
def test_deploy(accounts, chain, pm, owner, timelock, lendingPool, GeVault, roerouter):
  with brownie.reverts("GEV: Invalid Treasury"): 
    GeVault.deploy(NULL, roerouter, UNISWAPPOOLV3, 0, "GeVault WETHUSDC", "GEV-ETHUSDC", WETH, True, {"from": owner})
  
  g = GeVault.deploy(TREASURY, roerouter, UNISWAPPOOLV3, 0, "GeVault WETHUSDC", "GEV-ETHUSDC", WETH, True, {"from": owner})
  assert g.latestAnswer() == 0
  
  
# Deploy contract
def test_push_overlap(accounts, chain, pm, owner, timelock, lendingPool, gevault, roerouter):
  first_tick = gevault.ticks(0)
  with brownie.reverts("GEV: Push Tick Overlap"): gevault.pushTick(first_tick, {"from": owner})
  last_tick = gevault.ticks(gevault.getTickLength()-1)
  with brownie.reverts("GEV: Push Tick Overlap"): gevault.pushTick(last_tick, {"from": owner})
  
  with brownie.reverts("GEV: Shift Tick Overlap"): gevault.shiftTick(first_tick, {"from": owner})
  with brownie.reverts("GEV: Shift Tick Overlap"): gevault.shiftTick(last_tick, {"from": owner})
  

def test_disabled(accounts, chain, pm, usdc, owner, timelock, lendingPool, gevault, roerouter, oracle, TokenisableRange):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.setEnabled(False, {"from": owner})
  with brownie.reverts("GEV: Pool Disabled"): gevault.deposit(usdc, 1e6, {"from": owner})
  
  gevault.setEnabled(True, {"from": owner})
  gevault.deposit(usdc, 1e6, {"from": owner})
  
  
@pytest.mark.skip_coverage
def test_oracle_check_up(accounts, chain, pm, usdc, weth, owner, timelock, lendingPool, gevault, roerouter, oracle, TokenisableRange, routerV3, interface):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1e6, {"from": owner})
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})

  assert gevault.poolMatchesOracle() == True
  
  # move price downward by dumping much WETH
  aaveUSDC = accounts.at(AAVE_USDC, force=True)
  aaveWETH = accounts.at(AAVE_WETH, force=True)
  usdc.approve(routerV3, 2**256-1, {"from": aaveUSDC} )
  weth.approve(routerV3, 2**256-1, {"from": aaveWETH} )
  slot0 = interface.IUniswapV3Pool(UNISWAPPOOLV3).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  exactSwap(routerV3, [usdc, weth, 500, aaveUSDC, 1803751170519, 38000000e6, 0, 0], {"from": aaveUSDC})
  slot0 = interface.IUniswapV3Pool(UNISWAPPOOLV3).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  # price is now 1380.95
  assert gevault.poolMatchesOracle() == False
  
@pytest.mark.skip
@pytest.mark.skip_coverage
def test_oracle_check_down(accounts, chain, pm, usdc, weth, owner, timelock, lendingPool, gevault, roerouter, oracle, TokenisableRange, routerV3, interface):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1e6, {"from": owner})
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})

  assert gevault.poolMatchesOracle() == True
  
  # move price downward by dumping much WETH
  aaveUSDC = accounts.at(AAVE_USDC, force=True)
  aaveWETH = accounts.at(AAVE_WETH, force=True)
  usdc.approve(routerV3, 2**256-1, {"from": aaveUSDC} )
  weth.approve(routerV3, 2**256-1, {"from": aaveWETH} )
  slot0 = interface.IUniswapV3Pool(UNISWAPPOOLV3).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  exactSwap(routerV3, [weth, usdc, 500, aaveWETH, 1803751170519, 30000e18, 0, 0], {"from": aaveWETH})
  slot0 = interface.IUniswapV3Pool(UNISWAPPOOLV3).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  # price is now 1160
  assert gevault.poolMatchesOracle() == False
  

def test_deposit_withdraw_usdc(accounts, chain, pm, usdc, owner, timelock, lendingPool, gevault, roerouter, oracle, TokenisableRange):
  print ("ETH price", oracle.getAssetPrice(WETH))
  print ("vault value", gevault.getTVL())
  
  # the vault is properly balanced, we add USDC, should add equal balance in both tickers
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1e6, {"from": owner})
  print("GEV tvl", gevault.getTVL())
  assert nearlyEqual(gevault.getTVL(), oracle.getAssetPrice(usdc))
  t1 = TokenisableRange.at(gevault.ticks(1))
  t2 = TokenisableRange.at(gevault.ticks(2))
  assert gevault.getTickBalance(1) > 0 and gevault.getTickBalance(2) > 0
  assert nearlyEqual(gevault.getTickBalance(1) * t1.latestAnswer(), gevault.getTickBalance(2) * t2.latestAnswer()) # current index is 1, ticks 1, 2 are USDC, tick 3, 4 are WETH
  
  liquidity = gevault.balanceOf(owner)
  gevault.deposit(usdc, 1e6, {"from": owner})
  assert liquidity == gevault.balanceOf(owner)
  
  gevault.withdraw(liquidity / 2, usdc, {"from": owner})
  

def test_deposit_withdraw_weth(accounts, usdc, weth, owner, lendingPool, gevault, oracle, TokenisableRange):
  print ("ETH price", oracle.getAssetPrice(WETH))
  print ("vault value", gevault.getTVL())
  
  # the vault is properly balanced, we add WETH, should add equal balance in both tickers
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})
  print("GEV tvl", gevault.getTVL())
  assert nearlyEqual(gevault.getTVL(), oracle.getAssetPrice(weth))
  t3 = TokenisableRange.at(gevault.ticks(3))
  t4 = TokenisableRange.at(gevault.ticks(4))
  assert gevault.getTickBalance(3) > 0 and gevault.getTickBalance(4) > 0
  assert nearlyEqual(gevault.getTickBalance(3) * t3.latestAnswer(), gevault.getTickBalance(4) * t4.latestAnswer()) # current index is 4, ticks 4, 5 are USDC, tick 6, 7 are WETH
  
  liquidity = gevault.balanceOf(owner)
  gevault.deposit(weth, 1e18, {"from": owner})
  assert liquidity == gevault.balanceOf(owner)
  
  gevault.withdraw(liquidity / 2, weth, {"from": owner})


@pytest.mark.skip_coverage
def test_deposit_withdraw_eth(accounts, usdc, weth, owner, lendingPool, gevault, oracle, TokenisableRange):
  print ("ETH price", oracle.getAssetPrice(WETH))
  print ("vault value", gevault.getTVL())
  weth.withdraw(1e18, {"from": owner})
  
  with brownie.reverts("GEV: Deposit Zero"): gevault.deposit(weth, 0, {"from": owner})
  with brownie.reverts("GEV: Invalid Weth"): gevault.deposit(usdc, 0, {"from": owner, "value": 1e18})
  
  ethbal = owner.balance()
  gevault.deposit(weth, 0, {"from": owner, "value": 1e18})
  print("GEV tvl", gevault.getTVL())
  assert owner.balance() + 1e18 == ethbal
  assert nearlyEqual(gevault.getTVL(), oracle.getAssetPrice(weth))
  t3 = TokenisableRange.at(gevault.ticks(3))
  t4 = TokenisableRange.at(gevault.ticks(4))
  assert gevault.getTickBalance(3) > 0 and gevault.getTickBalance(4) > 0
  assert nearlyEqual(gevault.getTickBalance(3) * t3.latestAnswer(), gevault.getTickBalance(4) * t4.latestAnswer()) # current index is 4, ticks 4, 5 are USDC, tick 6, 7 are WETH
  
  liquidity = gevault.balanceOf(owner)
  gevault.withdraw(liquidity / 2, weth, {"from": owner})
  assert nearlyEqual( owner.balance() + 5e17 , ethbal)
    

@pytest.mark.skip
def test_max_cap(accounts, weth, owner, lendingPool, gevault, oracle, TokenisableRange):
  newCap = 1e14
  gevault.setTvlCap(newCap)
  assert gevault.tvlCap() == newCap;
  print("0")
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})
  print("1")
  liquidity = gevault.balanceOf(owner)
  # TVL is now $1262
  print("0#liq", liquidity)
  gevault.setTvlCap(1e11) # sets max tvl to $1k
  print("4")
  with brownie.reverts("GEV: Max Cap Reached"): gevault.deposit(weth, 5e17, {"from": owner})
  print("5")
  # Remove 90% liquidity, should remain ~$120 in the pool
  gevault.withdraw(liquidity / 1.1, weth, {"from": owner})
  print("6")
  # Now adding ~600 should work 
  gevault.deposit(weth, 5e17, {"from": owner})
  

@pytest.mark.skip_coverage
def test_rebalance_down(accounts, interface, weth, usdc, owner, gevault, oracle, routerV3, lendingPool, HardcodedPriceOracle):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1000e6, {"from": owner})
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})

  # initially the tickIndex is 1
  assert gevault.getActiveTickIndex() == 1
  
  # move price downward by dumping much WETH
  aaveUSDC = accounts.at(AAVE_USDC, force=True)
  aaveWETH = accounts.at(AAVE_WETH, force=True)
  usdc.approve(routerV3, 2**256-1, {"from": aaveUSDC} )
  weth.approve(routerV3, 2**256-1, {"from": aaveWETH} )
  POOL="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640" # ETH univ3 ETH-USDC 0.05%
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  exactSwap(routerV3, [weth, usdc, 500, aaveWETH, 1803751170519, 30000e18, 0, 0], {"from": aaveWETH})
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  # price is now 1160
  
  # after rebalancing, tick 3 should have assets while tick 7 should have nothing
  for k in range(gevault.getTickLength()):
    tkp = lendingPool.getReserveData(gevault.ticks(k))[7]
    print('bal', k, interface.ERC20(tkp).balanceOf(gevault))

  # we moved 1 tick down so new lower tick should be 0
  assert gevault.getActiveTickIndex() == 0
  
  # failure bc price moved, possible sandwich attack
  with brownie.reverts("GEV: Oracle Error"): gevault.rebalance({"from": owner})
  
  # deploy fixed price oracle
  print("old oracle price", oracle.getAssetPrice(weth))
  neworacle = HardcodedPriceOracle.deploy(116000000000, {"from": owner})
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  oracle.setAssetSources([WETH], [neworacle], {"from": poolAdmin})
  print("new oracle price", oracle.getAssetPrice(weth))
  gevault.rebalance({"from": owner})

  for k in range(gevault.getTickLength()):
    tkp = lendingPool.getReserveData(gevault.ticks(k))[7]
    print('bal', k, interface.ERC20(tkp).balanceOf(gevault))
  

@pytest.mark.skip_coverage
def test_rebalance_up(accounts, interface, weth, usdc, owner, gevault, oracle, routerV3, lendingPool, HardcodedPriceOracle):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1000e6, {"from": owner})
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})

  # initially the tickIndex is 1
  assert gevault.getActiveTickIndex() == 1
  
  # move price upward by buying much WETH
  aaveUSDC = accounts.at(AAVE_USDC, force=True)
  aaveWETH = accounts.at(AAVE_WETH, force=True)
  usdc.approve(routerV3, 2**256-1, {"from": aaveUSDC} )
  weth.approve(routerV3, 2**256-1, {"from": aaveWETH} )
  POOL="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640" # ETH univ3 ETH-USDC 0.05%
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  exactSwap(routerV3, [usdc, weth, 500, aaveUSDC, 1803751170519, 38000000e6, 0, 0], {"from": aaveUSDC})
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  # price is now 1380.95
  
  for k in range(gevault.getTickLength()):
    tkp = lendingPool.getReserveData(gevault.ticks(k))[7]
    print('bal', k, interface.ERC20(tkp).balanceOf(gevault))

  # we moved 1 tick up so new lower tick should be 2
  assert gevault.getActiveTickIndex() == 2

  # failure bc price moved, possible sandwich attack
  with brownie.reverts("GEV: Oracle Error"): gevault.rebalance({"from": owner})
  
  # deploy fixed price oracle
  print("old oracle price", oracle.getAssetPrice(weth))
  neworacle = HardcodedPriceOracle.deploy(138000000000, {"from": owner})
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  oracle.setAssetSources([WETH], [neworacle], {"from": poolAdmin})
  print("new oracle price", oracle.getAssetPrice(weth))
  gevault.rebalance({"from": owner})

  # after rebalancing, tick 5 should have assets while tick 1 should have nothing
  for k in range(gevault.getTickLength()):
    tkp = lendingPool.getReserveData(gevault.ticks(k))[7]
    print('bal', k, interface.ERC20(tkp).balanceOf(gevault))
  

@pytest.mark.skip
@pytest.mark.skip_coverage
# Trying to rebalance upward, but the lower ticker has some outstanding debt, so not all can be moved
def test_rebalance_with_debt(accounts, interface, weth, usdc, owner, user, gevault, oracle, routerV3, lendingPool, HardcodedPriceOracle, TokenisableRange):
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1262e6, {"from": owner})
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})

  # initially the tickIndex is 1
  assert gevault.getActiveTickIndex() == 1
  
  # user borrows some of the 1st tick
  t1 = gevault.ticks(1)
  lendingPool.borrow(t1, 100e18, 2, 0, user, {"from": user})

  # move price upward by buying much WETH
  aaveUSDC = accounts.at(AAVE_USDC, force=True)
  aaveWETH = accounts.at(AAVE_WETH, force=True)
  usdc.approve(routerV3, 2**256-1, {"from": aaveUSDC} )
  weth.approve(routerV3, 2**256-1, {"from": aaveWETH} )
  POOL="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640" # ETH univ3 ETH-USDC 0.05%
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  exactSwap(routerV3, [usdc, weth, 500, aaveUSDC, 1803751170519, 38000000e6, 0, 0], {"from": aaveUSDC})
  slot0 = interface.IUniswapV3Pool(POOL).slot0()
  print('slot0', slot0, slot0[0], 1/((slot0[0]**2)/2**192) * 1e12)
  # price is now 1380.95
  
  
  for k in range(gevault.getTickLength()):
    print('bal', k, gevault.getTickBalance(k))

  # we moved 1 tick up so new lower tick should be 2
  assert gevault.getActiveTickIndex() == 2

  # failure bc price moved, possible sandwich attack
  with brownie.reverts("GEV: Oracle Error"): gevault.rebalance({"from": owner})
  
  # deploy fixed price oracle
  print("old oracle price", oracle.getAssetPrice(weth))
  neworacle = HardcodedPriceOracle.deploy(138000000000, {"from": owner})
  #0xBcca60bB61934080951369a648Fb03DF4F96263C

  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  oracle.setAssetSources([WETH], [neworacle], {"from": poolAdmin})
  print("new oracle price", oracle.getAssetPrice(weth))
  gevault.rebalance({"from": owner})

  for k in range(gevault.getTickLength()):
    print('bal', k, gevault.getTickBalance(k))
    
  # assert that all remaining available supply has been moved away when rebalancing
  assert interface.ERC20(lendingPool.getReserveData(t1)[7]).balanceOf(lendingPool) == 0
  

@pytest.mark.skip
def test_fees(accounts, weth, usdc, owner, lendingPool, gevault, oracle, TokenisableRange):
  # getAdjustedBaseFee(increaseToken0): increaseToken0 is True if depositing token0 (here: usdc) or withdrawing token1
  baseFee = gevault.baseFeeX4()
  # vault is empty, so increasing token1 should get half fees
  assert gevault.getAdjustedBaseFee(False) == baseFee / 2
  print("base fee vs adjusted", baseFee, gevault.getAdjustedBaseFee(False) )
  
  # Deposit WETH
  weth.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(weth, 1e18, {"from": owner})
  # pool now is imbalanced with only WETH, so fee for depositing USDC should be halved, fee for WETH should be maxxed out (to +50%)
  assert gevault.getAdjustedBaseFee(False) == baseFee * 1.5
  assert gevault.getAdjustedBaseFee(True) == baseFee / 2
  
  # Deposit USDC, 20% more than ETH in value
  usdc.approve(gevault, 2**256-1, {"from": owner})
  gevault.deposit(usdc, 1262e6 * 1.2, {"from": owner})
  # Pool is imbalanced, with valueUSDC = 1.2 * valueWETH, fee for depositing more USDC should be around 1.2 * baseFee,  -0/-1 for rounding
  print("fees", gevault.getAdjustedBaseFee(True), baseFee, baseFee * 1.2, baseFee * 1.2 - 1)
  assert gevault.getAdjustedBaseFee(True) == baseFee * 1.2 or gevault.getAdjustedBaseFee(True) == baseFee * 1.2 - 1
  print("fees", gevault.getAdjustedBaseFee(False), baseFee, baseFee / 1.2)
  assert gevault.getAdjustedBaseFee(False) == baseFee / 1.2

