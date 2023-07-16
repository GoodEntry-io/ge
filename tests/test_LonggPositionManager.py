import pytest, brownie


# CONSTANTS
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WETHUSDC = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
TREASURY="0x50101017adf9D2d06C395471Bc3D6348589c3b97" # random empty
ROUTER="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
LENDING_POOL_ADDRESSES_PROVIDER = "0x01b76559D512Fa28aCc03630E8954405BcBB1E02"

LOTS_LP = "0xec08867a12546ccf53b32efb8c23bb26be0c04f1"
AAVE_WETH = "0x030ba81f1c18d280636f32af80b9aad02cf0854e"
AAVE_USDC = "0xbcca60bb61934080951369a648fb03df4f96263c"
NULL =      "0x0000000000000000000000000000000000000000"

@pytest.fixture(scope="module", autouse=True)
def weth(interface, accounts):
  weth = interface.ERC20(WETH)
  yield weth

@pytest.fixture(scope="module", autouse=True)
def usdc(interface, accounts):
  usdc  = interface.ERC20(USDC)
  yield usdc

@pytest.fixture(scope="module", autouse=True)
def wethusdc(interface, accounts):
  wethusdc = interface.IUniswapV2Pair(WETHUSDC)
  yield wethusdc

@pytest.fixture(scope="module", autouse=True)
def router(interface):
  router = interface.IUniswapV2Router01(ROUTER)
  yield router
  
@pytest.fixture(scope="module", autouse=True)
def roerouter(RoeRouter, owner):
  roerouter = RoeRouter.deploy(TREASURY, {"from": owner})
  roerouter.addPool(LENDING_POOL_ADDRESSES_PROVIDER, USDC, WETH, ROUTER, {"from": owner})
  yield roerouter

@pytest.fixture(scope="module", autouse=True)
def pm(LonggPositionManager, owner, roerouter):
  pm = LonggPositionManager.deploy(roerouter, {"from": owner})
  yield pm
  
@pytest.fixture(scope="module", autouse=True)
def lendingPool(interface, accounts):
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  try:
    lpadd.setLendingPoolImpl("0x09add1BC0CaC5FD269CE5eceA034e218bF16FA76", {"from": poolAdmin}) # Set to correct implementation
  except: 
    pass
  config = interface.ILendingPoolConfigurator(lpadd.getLendingPoolConfigurator());
  lendingPool = interface.ILendingPool(lpadd.getLendingPool())
  lendingPool.setSoftLiquidationThreshold(102e16, {"from": poolAdmin})
  config.enableBorrowingOnReserve(WETHUSDC, False, {"from": poolAdmin})
  yield lendingPool  


@pytest.fixture(scope="module", autouse=True)
def oracle(interface, accounts):
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  oracle = interface.IAaveOracle(lpadd.getPriceOracle())
  yield oracle
  

# Call to seed accounts before isolation tests
@pytest.fixture(scope="module", autouse=True)
def seed_accounts( interface, weth, usdc, wethusdc, user, user2, owner, lendingPool, accounts):
  try: 
    lotsLP = accounts.at(LOTS_LP, force=True)
    aaveUSDC = accounts.at(AAVE_USDC, force=True)
    aaveWETH = accounts.at(AAVE_WETH, force=True)
    
    weth.approve(lendingPool, 2**256-1, {"from": aaveWETH})
    weth.transfer(owner, 10e18, {"from": aaveWETH})
    weth.transfer(user, 10e18, {"from": aaveWETH})
    lendingPool.deposit(weth, 30e18, aaveWETH, 0, {"from": aaveWETH}) 
    lendingPool.deposit(weth, 1e18, user2, 0, {"from": aaveWETH}) 
    lendingPool.deposit(weth, 1e18, user, 0, {"from": aaveWETH}) 
    
    usdc.approve(lendingPool, 2**256-1, {"from": aaveUSDC})
    usdc.transfer(user, 1e10, {"from": aaveUSDC})
    usdc.transfer(owner, 1e10, {"from": aaveUSDC})
    lendingPool.deposit(usdc, 1e10, user2, 0, {"from": aaveUSDC}) 
    lendingPool.deposit(usdc, 1e12, aaveUSDC, 0, {"from": aaveUSDC}) 
    
    wethusdc.approve(lendingPool, 2**256-1, {"from": lotsLP})
    lendingPool.deposit(wethusdc, 5e16, lotsLP, 0, {"from": lotsLP}) 
  except:
    pass

@pytest.fixture(scope="module", autouse=True)
def config(interface, accounts):
  lpAdd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  config = interface.ILendingPoolConfigurator(lpAdd.getLendingPoolConfigurator() )
  yield config

# close remaining position as sometimes it's left in unclean state
def clean(lendingPool, user2, lpToken, weth, router, pm):
  if lendingPool.getUserAccountData(user2)[1] > 0:
    try: pm.close(poolId, lpToken, 1e40, weth, {"from": user2})
    except: pass


# Check if 2 vaslues are within 1%
def nearlyEqual(value0, value1):
  if (value1 == 0): return value1 == value0
  else: return abs (value0-value1) / value1 < 0.01


# No isolation when testing uniswap as it will cause reentrancy reverts
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass
  
  

# Build a leverage position
def test_position(accounts, chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  lpToken = wethusdc
  poolId = roerouter.getPoolsLength() - 1

  with brownie.reverts("59"): # Aave no credit delegation
    pm.openOneSidedPosition(poolId, lpToken, 1e13, usdc, 100, {"from": user2})

  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.open(poolId, lpToken, 1e12, {"from": user2}) #open position 
  
  with brownie.reverts("11"):
    pm.open(poolId, lpToken, 5e16, {"from": user2}) # Aave '11' , not enough collateral to borrow

  with brownie.reverts("42"):
    pm.liquidate(poolId, user2, lpToken, 1e11, weth, {"from": owner} ) # Aave '42' Health factor not below threshold: cant liquidate
  
  with brownie.reverts("Not initiated by user"): # ROE health factor above threshold: cant deleverage position
    pm.softLiquidateLP(poolId, user2, lpToken, 1e11, usdc, {"from": owner} )

  pm.close(poolId, lpToken, 1e9, usdc, {"from": user2}) #close partially
  pm.close(poolId, lpToken, 0, usdc, {"from": user2}) #close all
  
  # Open position and sell USDC
  with brownie.reverts("LPM: Invalid Percentage"):
    pm.openOneSidedPosition(poolId, lpToken, 1e13, usdc, 110, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, 1e13, usdc, 100, {"from": user2})
  pm.close(poolId, lpToken, 0, usdc, {"from": user2}) #close all
  
  # Open position and sell WETH
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, 1e12, weth, 100, {"from": user2})
  pm.close(poolId, lpToken, 1e40, weth, {"from": user2}) #debt repaid, 1e40 larger than actual debt will just repay all

  
# Deposit collateral and open position
def test_unallowed_flashloan_call(pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  from eth_abi import encode_abi

  # levearge call unallowed
  calldata = encode_abi(['uint8', 'address', 'address', 'uint', 'address', 'uint'], [0, owner.address, NULL, 0, NULL, poolId])
  with brownie.reverts("LPM: Call Unallowed"):
    pm.executeOperation([], [], [], owner, calldata, {"from": owner})

  # flash liquidation call unallowed
  calldata = encode_abi(['uint8', 'address', 'address', 'uint', 'address', 'uint'], [1, owner.address, WETHUSDC, 1, USDC, poolId])
  with brownie.reverts("LPM: Call Unallowed"):
    pm.executeOperation([wethusdc], [1], [], owner, calldata, {"from": owner})
  

# Deposit collateral and open position w/ token0
def test_open_with_collateral_USDC(pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  borrowLP = 1e8
  clean(lendingPool, user, lpToken, weth, router, pm)

  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user})
  usdc.approve(pm, 2**256-1, {"from": user})
  pm.depositCollateralAndOpen(poolId, usdc, 10e6, lpToken, borrowLP, {"from": user})
  assert lendingPool.getUserAccountData(user)[1] ==  borrowLP * oracle.getAssetPrice(WETHUSDC) / 10**18 # check debt is worth 1e8
  
  # withdraw collateral w/ closeAndWithdrawCollateral
  pm.closeAndWithdrawCollateral(poolId, lpToken, borrowLP*2, usdc, {"from": user} )
  assert lendingPool.getUserAccountData(user)[1] ==  0


# Deposit collateral and open position w/ token1
def test_open_with_collateral_ETH(pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  borrowLP = 1e8
  clean(lendingPool, user, lpToken, weth, router, pm)

  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user})
  weth.approve(pm, 2**256-1, {"from": user})
  pm.depositCollateralAndOpen(poolId, weth, 1e16, lpToken, borrowLP, {"from": user})
  assert lendingPool.getUserAccountData(user)[1] ==  borrowLP * oracle.getAssetPrice(WETHUSDC) / 10**18 # check debt is worth 1e8
  
  # withdraw collateral w/ closeAndWithdrawCollateral
  pm.closeAndWithdrawCollateral(poolId, lpToken, borrowLP*2, weth, {"from": user} )
  assert lendingPool.getUserAccountData(user)[1] ==  0


# Build a leverage position
def test_unhealthy_usdc_position(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  # close remaining position as sometimes it's left in unclean state
  clean(lendingPool, user2, lpToken, weth, router, pm)

  # calculate how much to borrow 
  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5e18
  
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  with brownie.reverts("LPM: Invalid Swap Source"):
    pm.openOneSidedPosition(poolId, lpToken, toBorrow, ROUTER, 100, {"from": user2}) # swap all for bogus token
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, usdc, 100, {"from": user2}) # borrow LPs and swap all for USDC
  print(lendingPool.getUserAccountData(user2)[5]/1e18)

  # sleep until HF < 1.02 (can be soft liquidated)
  #while lendingPool.getUserAccountData(user2)[5]/1e18 > 1.02:
  chain.sleep(650000000); chain.mine(1);
  #print('uup', lendingPool.getUserAccountData(user2)[5]/1e18)
  
  # fail if we want to soft liquidate too much debt
  with brownie.reverts("LPM: Reduce Too Much"):
    pm.softLiquidateLP(poolId, user2, lpToken, toBorrow, weth, {"from": owner} )
    
  # softLiquidate lpToken and receive fee as weth
  liquidateAmount = 1e12
  pm.softLiquidateLP(poolId, user2, lpToken, liquidateAmount, weth, {"from": owner} )
  liquidationFee = liquidateAmount * oracle.getAssetPrice(lpToken) * 0.01 / oracle.getAssetPrice(weth)
  print(liquidationFee, weth.balanceOf(TREASURY))
   # treasury received a 1+/-0.01% graceful deleveraging fee (error margin bc of a potential swap that changes LP value during liquidation
  assert abs(weth.balanceOf(TREASURY) - liquidationFee ) / liquidationFee < 0.01 
  
  print('health',lendingPool.getUserAccountData(user2)[5]/1e18)
  with brownie.reverts("42"):
    pm.liquidate(poolId, user2, lpToken, 1e11, weth, {"from": owner} ) # AAve '42' Health factor not below threshold

  # sleep until FH < 1
  #while lendingPool.getUserAccountData(user2)[5]/1e18 > 1 and max < 100:
  chain.sleep(200000000); chain.mine(1);
  print('health2', lendingPool.getUserAccountData(user2)[5]/1e18)
  # once HF < 1, soft liquidation isnt possible anymore
  with brownie.reverts("LPM: HF Too Low"):
    pm.softLiquidateLP(poolId, user2, lpToken, liquidateAmount, weth, {"from": owner} ) 

  # liquidate a little of the position and return weth
  pm.liquidate(poolId, user2, lpToken, 1e11, weth, {"from": owner} )
  # liquidate and return usdc
  pm.liquidate(poolId, user2, lpToken, 1e11, usdc, {"from": owner} )


# Build a leverage position
def test_unhealthy_usdc_position_dualdebt(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  # close remaining position as sometimes it's left in unclean state
  clean(lendingPool, user2, lpToken, weth, router, pm)

  # calculate how much to borrow 
  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5e18
  
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, usdc, 100, {"from": user2}) # borrow LPs and swap all for USDC

  lendingPool.borrow(USDC, 100e6, 2, 0, user2, {"from": user2})

  # fail as we are trying to remove all collateral while repaying only the lpToken debt and leaving the USDC debt
  with brownie.reverts("LPM: HF Too Low"):
    pm.closeAndWithdrawCollateral(poolId, lpToken, 0, weth, {"from": user2} )
  
  
def test_unhealthy_weth_position(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  # close remaining position as sometimes it's left in unclean state
  clean(lendingPool, user2, lpToken, weth, router, pm)

  # calculate how much to borrow
  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5.2e18
  
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, weth, 100, {"from": user2}) # borrow LPs and swap all for USDC

  
  #print(lendingPool.getUserAccountData(user2)[5]/1e18) 
  #while lendingPool.getUserAccountData(user2)[5]/1e18 > 1.02:
  chain.sleep(600000000); chain.mine(1);
  print(lendingPool.getUserAccountData(user2)[5]/1e18) 
  
  lpAmount = 1e12
  liquidationFee = lpAmount * oracle.getAssetPrice(lpToken) * 0.01 / oracle.getAssetPrice(usdc) / 10**(lpToken.decimals() - usdc.decimals())
  pm.softLiquidateLP(poolId, user2, lpToken, lpAmount, usdc, {"from": owner} )
   # treasury received a 1+/-0.01% graceful deleveraging fee (error margin bc of a potential swap that changes LP value during liquidation
  assert abs(usdc.balanceOf(TREASURY) - liquidationFee ) / liquidationFee < 0.01 

  while lendingPool.getUserAccountData(user2)[5]/1e18 > 1:
    chain.sleep(2000000000); chain.mine(1);
    #print(lendingPool.getUserAccountData(user2)[5]/1e18)
    
  # liquidate a little of the position and return weth
  pm.liquidate(poolId, user2, lpToken, 1e11, weth, {"from": owner} )
  # liquidate and return usdc
  pm.liquidate(poolId, user2, lpToken, 1e11, usdc, {"from": owner} )


# Test soft liquidating any debt by transferring the tokens in from the liquidator
def test_reduce_nonLP(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1

  clean(lendingPool, user2, wethusdc, weth, router, pm)

  toBorrow = lendingPool.getUserAccountData(user2)[2] / oracle.getAssetPrice(USDC) * 1e6 * 0.91
  lendingPool.borrow(usdc, toBorrow, 2, 0, user2, {"from": user2})

  # sleep until user HF < 1.02 (and can be soft liquidated)
  print('health', lendingPool.getUserAccountData(user2)[5]/1e18) 
  chain.sleep(10000000000); chain.mine(1);    
  print('health22', lendingPool.getUserAccountData(user2)[5]/1e18) 
  chain.sleep(1000000000); chain.mine(1);    
  usdc.approve(pm, 2**256-1, {"from": owner})
  repayAmount = 1e8

  print('health3', lendingPool.getUserAccountData(user2)[5]/1e18) 
  pm.softLiquidate(poolId, user2, usdc, repayAmount, weth, {"from": owner} )
  liquidationFee = repayAmount * oracle.getAssetPrice(usdc) * 0.01 / oracle.getAssetPrice(weth) / 10**(usdc.decimals() - weth.decimals())
  # treasury received a 1+/-0.01% graceful deleveraging fee (error margin bc of a potential swap that changes LP value during liquidation
  assert abs(weth.balanceOf(TREASURY) - liquidationFee ) / liquidationFee < 0.01 
  
  # sleep until HF < 1
  chain.sleep(11000000000); chain.mine(1);
  print('health2', lendingPool.getUserAccountData(user2)[5]/1e18) 
  # cant soft liquidate when HF < 1
  with brownie.reverts("LPM: HF Too Low"): pm.softLiquidate(poolId, user2, usdc, repayAmount, weth, {"from": owner} )


# Check that the position manager correctly prevents sandwich attacks when closing positions
def test_sandwich_attack(accounts, chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc

  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.open(poolId, lpToken, 1e14, {"from": user2})
  
  # dislocate uniswap pool: oracle price wont match 
  lotsUsdc = accounts.at(AAVE_USDC, force=True)
  usdc.approve(router, 2**256-1, {"from": lotsUsdc})
  router.swapExactTokensForTokens(5e12, 0, [usdc.address, weth.address], lotsUsdc, chain.time()+86400, {"from": lotsUsdc}) 
  with brownie.reverts('PM: LP Oracle Error'):
    pm.close(poolId, lpToken, 1e40, weth, {"from": user2}) 
  
  # dislocate in the other direction
  lotsWETH = accounts.at(AAVE_WETH, force=True)
  weth.approve(router, 2**256-1, {"from": lotsWETH})
  router.swapExactTokensForTokens(10e21, 0, [weth.address, usdc.address], lotsWETH, chain.time()+86400, {"from": lotsWETH})
  with brownie.reverts('PM: LP Oracle Error'):
    pm.close(poolId, lpToken, 1e40, weth, {"from": user2}) 


# Check that the position manager correctly prevents sandwich attacks when opening positions
def test_sandwich_attack_on_open(accounts, chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc

  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})

  # dislocate uniswap pool: oracle price wont match 
  lotsUsdc = accounts.at(AAVE_USDC, force=True)
  usdc.approve(router, 2**256-1, {"from": lotsUsdc})
  router.swapExactTokensForTokens(5e12, 0, [usdc.address, weth.address], lotsUsdc, chain.time()+86400, {"from": lotsUsdc}) 
  with brownie.reverts():
    pm.openOneSidedPosition(poolId, lpToken, 1e14, usdc, 100, {"from": user2})


def test_deltaNeutralize_up(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  clean(lendingPool, user2, lpToken, weth, router, pm)

  # calculate how much to borrow
  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5.2e18
  
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, weth, 100, {"from": user2}) # borrow LPs and swap all for USDC

  # delta neutralize 
  pm.deltaNeutralize(poolId, lpToken, weth, {"from": user2})
  # check user weth balance
  roeWethBal = interface.ERC20(lendingPool.getReserveData(weth)[7]).balanceOf(user2)
  debt = interface.ERC20(lendingPool.getReserveData(lpToken)[9]).balanceOf(user2)
  resA, resB, ts = interface.IUniswapV2Pair(lpToken).getReserves() # resA is USDC, resB is WETH on ETH
  owedWeth = resB * debt / interface.IUniswapV2Pair(lpToken).totalSupply()
  assert abs( roeWethBal - owedWeth ) * 1e6 < owedWeth # discrepancy should be lower than USDC granularity (1e6 vs LP has 1e18 decimals)
  

def test_deltaNeutralize_down(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, oracle, roerouter):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  clean(lendingPool, user2, lpToken, weth, router, pm)

  # calculate how much to borrow
  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5.2e18
  
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, weth, 100, {"from": user2}) # borrow LPs and swap all for USDC
  
  roeUsdcBal = interface.ERC20(lendingPool.getReserveData(usdc)[7]).balanceOf(user2)
  print ( 'roeusdc', roeUsdcBal)
  # delta neutralize 
  pm.deltaNeutralize(poolId, lpToken, usdc, {"from": user2})
  # check user weth balance
  
  roeUsdcBal = interface.ERC20(lendingPool.getReserveData(usdc)[7]).balanceOf(user2)
  print ( 'roeusdc', roeUsdcBal)
  debt = interface.ERC20(lendingPool.getReserveData(lpToken)[9]).balanceOf(user2)
  print ( 'debt', debt)
  resA, resB, ts = interface.IUniswapV2Pair(lpToken).getReserves() # resA is USDC, resB is WETH on ETH
  print ( 'res', resA, resB)
  owedUsdc = resA * debt / interface.IUniswapV2Pair(lpToken).totalSupply()
  print ( 'owedUsdc', owedUsdc)
  print('diff bal,  debt, diff', roeUsdcBal, owedUsdc, roeUsdcBal - owedUsdc)
  assert abs( roeUsdcBal - owedUsdc ) * 1e5 < owedUsdc # discrepancy should be lower than USDC granularity 
  
  #other way 
  pm.deltaNeutralize(poolId, lpToken, weth, {"from": user2})
  roeWethBal = interface.ERC20(lendingPool.getReserveData(weth)[7]).balanceOf(user2)
  print ( 'roeWethBal', roeWethBal)
  debt = interface.ERC20(lendingPool.getReserveData(lpToken)[9]).balanceOf(user2)
  
  print ( 'debt', debt)
  resA, resB, ts = interface.IUniswapV2Pair(lpToken).getReserves() # resA is USDC, resB is WETH on ETH
  print ( 'res', resA, resB)
  owedWeth = resB * debt / interface.IUniswapV2Pair(lpToken).totalSupply()
  print ( 'owedWeth', owedWeth)
  print('diff bal,  debt, diff', roeWethBal, owedWeth, roeWethBal - owedWeth)
  assert abs( roeWethBal - owedWeth ) * 1e5 < owedWeth # discrepancy should be lower than USDC granularity (1e6 vs LP has 1e18 decimals)


# Test that delta neutralizing a position cannot be sandwiched
def test_deltaNeutralize_sandwich(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, oracle, roerouter, accounts):
  lendingPool.PMAssign(pm, {"from": timelock })
  poolId = roerouter.getPoolsLength() - 1
  lpToken = wethusdc
  clean(lendingPool, user2, lpToken, weth, router, pm)

  toBorrow = lendingPool.getUserAccountData(user2)[0] / oracle.getAssetPrice(WETHUSDC) * 5.2e18
  interface.ICreditDelegationToken( lendingPool.getReserveData(lpToken)[9] ).approveDelegation(pm, 2**256-1, {"from": user2})
  pm.openOneSidedPosition(poolId, lpToken, toBorrow, weth, 100, {"from": user2}) # borrow LPs and swap all for USDC

  # dislocate uniswap pool: oracle price wont match 
  lotsUsdc = accounts.at(AAVE_USDC, force=True)
  usdc.approve(router, 2**256-1, {"from": lotsUsdc})
  router.swapExactTokensForTokens(5e12, 0, [usdc.address, weth.address], lotsUsdc, chain.time()+86400, {"from": lotsUsdc}) 

  with brownie.reverts("PM: LP Oracle Error"):
    pm.deltaNeutralize(poolId, lpToken, weth, {"from": user2})


def test_removeDust(chain, pm, owner, timelock, lendingPool, wethusdc, weth, usdc, user2, interface, router, oracle, roerouter):
  usdc.approve(pm, 2**256-1, {"from": owner})
  usdc.transfer(pm, 1e6, {"from": owner})
  pm.removeDust(usdc, {"from": owner})
  
  
def test_validateValuesAgainstOracle(pm, Test_LonggPositionManager, roerouter, oracle, usdc, weth, owner):
  test= Test_LonggPositionManager.deploy(roerouter, {"from": owner})
  priceUsdc = oracle.getAssetPrice(usdc)
  priceEth = oracle.getAssetPrice(weth)
  amountEth = 1e18
  amountUsdc = priceEth / priceUsdc * 1e6

  with brownie.reverts("PM: LP Oracle Error"):
    test.test_validateValuesAgainstOracle(oracle, usdc, 1e6, weth, 1e18, {"from": owner})
  test.test_validateValuesAgainstOracle(oracle, usdc, amountUsdc, weth, amountEth, {"from": owner})
  
  with brownie.reverts("PM: LP Oracle Error"):
    test.test_validateValuesAgainstOracle(oracle, weth, 1e18, usdc, 1e6, {"from": owner})
  test.test_validateValuesAgainstOracle(oracle, weth, amountEth, usdc, amountUsdc, {"from": owner})


# Test that swap target is properly calculated by the oracle
def test_getTargetAmountFromOracle(pm, Test_LonggPositionManager, roerouter, oracle, usdc, weth, owner, NullOracle):
  test = Test_LonggPositionManager.deploy(roerouter, {"from": owner})
  nullOracleUsd = NullOracle.deploy(usdc, {"from": owner})
  nullOracleEth = NullOracle.deploy(weth, {"from": owner})
  
  # Calculate equivalent amounts from local oracle
  priceUsdc = oracle.getAssetPrice(usdc)
  priceEth = oracle.getAssetPrice(weth)
  amountEth = 1e18
  amountUsdc = priceEth / priceUsdc * 1e6
  
  with brownie.reverts("LPM: Invalid Oracle Price"): test.test_getTargetAmountFromOracle(nullOracleUsd, usdc, amountUsdc, weth)
  with brownie.reverts("LPM: Invalid Oracle Price"): test.test_getTargetAmountFromOracle(nullOracleEth, usdc, amountUsdc, weth)
 
  amtEth = test.test_getTargetAmountFromOracle(oracle, usdc, amountUsdc, weth)
  assert nearlyEqual(amtEth, amountEth)

  amtUsdc = test.test_getTargetAmountFromOracle(oracle, weth, amountEth, usdc)
  assert nearlyEqual(amtUsdc, amountUsdc)
  
  # 1e8 Eth will return 0 USDC since below the USDC 6 decimals precision: 1268e8 = 0.1268e12
  with brownie.reverts("LPM: Target Amount Too Low"): test.test_getTargetAmountFromOracle(oracle, weth, 1e8, usdc)
  