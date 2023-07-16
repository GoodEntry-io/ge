import pytest, brownie
import math


# CONSTANTS
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WETHUSDC = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
TREASURY="0x50101017adf9D2d06C395471Bc3D6348589c3b97" # random empty
ROUTER="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
ROUTERV3="0xE592427A0AEce92De3Edee1F18E0157C05861564"
UNISWAPPOOLV3_3 = "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8" # ETH univ3 ETH-USDC 0.3%
UNISWAPPOOLV3 = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640" # ETH univ3 ETH-USDC 0.05%
# LPAD for btc 0xe7f6F6Cd1Be8313a05e0E38bA97B2A5Dfed7616d - for weth "0x01b76559D512Fa28aCc03630E8954405BcBB1E02"
LENDING_POOL_ADDRESSES_PROVIDER = "0x01b76559D512Fa28aCc03630E8954405BcBB1E02" 

AAVE_WETH = "0x030ba81f1c18d280636f32af80b9aad02cf0854e"
AAVE_USDC = "0xbcca60bb61934080951369a648fb03df4f96263c"
NULL =      "0x0000000000000000000000000000000000000000"

# Careful: ticker range now in middle of range, testing ticker
RANGE_LIMITS = [500, 1000, 2000, 2500, 5000]
RANGE_LIMITS = [1000, 1200, 1400, 1600, 1800]

@pytest.fixture(scope="module", autouse=True)
def weth(interface, accounts):
  # Claim WETH from MATIC-Aave pool
  aaveWETH = accounts.at("0x28424507fefb6f7f8e9d3860f56504e4e5f5f390", force=True)
  weth = interface.ERC20(WETH, owner=aaveWETH)
  yield weth

@pytest.fixture(scope="module", autouse=True)
def usdc(interface, accounts):
  # Claim USDC from Stargate stake account
  stargate = accounts.at("0x1205f31718499dBf1fCa446663B532Ef87481fe1", force=True)
  usdc  = interface.ERC20(USDC, owner=stargate)
  yield usdc


@pytest.fixture(scope="module", autouse=True)
def router(interface):
  router = interface.IUniswapV2Router01(ROUTER)
  yield router
  
@pytest.fixture(scope="module", autouse=True)
def routerV3(interface):
  routerV3 = interface.ISwapRouter(ROUTERV3)
  yield routerV3

@pytest.fixture(scope="module", autouse=True)
def roerouter(RoeRouter, owner):
  roerouter = RoeRouter.deploy(TREASURY, {"from": owner})
  roerouter.addPool(LENDING_POOL_ADDRESSES_PROVIDER, USDC, WETH, ROUTER, {"from": owner})
  yield roerouter
  
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
    AAVE_WETH = "0x030ba81f1c18d280636f32af80b9aad02cf0854e"
    AAVE_USDC = "0xbcca60bb61934080951369a648fb03df4f96263c"
    aaveUSDC = accounts.at(AAVE_USDC, force=True)
    aaveWETH = accounts.at(AAVE_WETH, force=True)

    weth.approve(lendingPool, 2**256-1, {"from": aaveWETH})
    weth.transfer(owner, 5e18, {"from": aaveWETH})
    lendingPool.deposit(weth, 30e18, owner, 0, {"from": aaveWETH}) 
    lendingPool.deposit(weth, 30e18, user, 0, {"from": aaveWETH}) 

    usdc.approve(lendingPool, 2**256-1, {"from": aaveUSDC})
    usdc.transfer(owner, 5e10, {"from": aaveUSDC})
    lendingPool.deposit(usdc, 30e10, owner, 0, {"from": aaveUSDC}) 
    lendingPool.deposit(usdc, 30e10, user, 0, {"from": aaveUSDC}) 

  except Exception as e:
    print(e)

@pytest.fixture(scope="module", autouse=True)
def contracts(owner, Strings, TickMath, TokenisableRange, UpgradeableBeacon, RangeManager, RangerPositionManager, roerouter, lendingPool, weth, usdc):
  Strings.deploy({"from": owner})
  TickMath.deploy({"from": owner})
  tr = TokenisableRange.deploy({"from": owner})
  trb = UpgradeableBeacon.deploy(tr, {"from": owner})
  r = RangeManager.deploy(lendingPool, usdc, weth, {"from": owner})
  rpm = RangerPositionManager.deploy(roerouter, {"from": owner})
  yield tr, trb, r, rpm


# calc range values for uni v3: https://docs.google.com/spreadsheets/d/1EXqXeXysknbib3_WbUB-lGGknBjxJvt4/edit#gid=385415845
# OR return values from https://app.uniswap.org/#/add/ETH/0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48/3000?chain=mainnet&maxPrice=2000&minPrice=1600
@pytest.fixture(scope="module", autouse=True)
def liquidityRatio(interface, usdc, weth):
  def liqRatio(rangeLow, rangeHigh):
    pool = interface.IUniswapV3Factory("0x1F98431c8aD98523631AE4a59f267346ea31F984").getPool(usdc, weth, 3000)
    sqrtPriceX96 = interface.IUniswapV3Pool(pool).slot0()[0]
    price = ( 2 ** 192 / sqrtPriceX96 ** 2 ) * 1e12 # 1e12 because decimal difference between WETH and USDC
    if price < rangeLow: price = rangeLow
    if price > rangeHigh: price = rangeHigh
    priceSqrt = math.sqrt( math.pow(1.0001, -math.log(math.sqrt(price)) * 2 / math.log(1.0001)))
    priceLowSqrt = math.sqrt( math.pow(1.0001, -math.log(math.sqrt(rangeLow)) * 2 / math.log(1.0001)))
    priceHighSqrt = math.sqrt( math.pow(1.0001, -math.log(math.sqrt(rangeHigh)) * 2 / math.log(1.0001)))
    if priceSqrt == priceLowSqrt: return 0, 1e18 / rangeLow
    relation = (priceSqrt-priceHighSqrt) / ( (1/priceSqrt) - (1/priceLowSqrt) )
    lpAmount = 1
    usdAmount = lpAmount / ( 1 + relation * price ) 
    ethAmount = relation * usdAmount
    return usdAmount * 1e6, ethAmount * 1e18
  yield liqRatio


# No isolation when testing uniswap as it will cause reentrancy reverts
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass
    


@pytest.fixture(scope="module", autouse=True)
def prep_ranger(accounts, owner, timelock, weth, usdc, interface, oracle, config, contracts, TokenisableRange, liquidityRatio):
  tr, trb, r, rpm = contracts

  ranges = [ [RANGE_LIMITS[0], RANGE_LIMITS[1]], [RANGE_LIMITS[1], RANGE_LIMITS[2]], [RANGE_LIMITS[2], RANGE_LIMITS[3]] ]
  for i in ranges:
    r.generateRange( i[0]*1e10, i[1]*1e10, i[0], i[1], trb, {"from": owner})

  # Approve rangeManager for initRange
  weth.approve(r, 2**256-1, {"from": owner})
  usdc.approve(r, 2**256-1, {"from": owner})

  for i in range(r.getStepListLength()):
    usdAmount, ethAmount = liquidityRatio( ranges[i][0], ranges[i][1])  
    r.initRange(r.tokenisedRanges(i), usdAmount, ethAmount, {"from": owner})
    usdAmount, ethAmount = liquidityRatio( (ranges[i][0]+ranges[i][1])/2,(ranges[i][0]+ranges[i][1])/2 + 1)
    r.initRange(r.tokenisedTicker(i), usdAmount, ethAmount, {"from": owner})  
  
  # Load all into Oracle
  addresses = [r.tokenisedRanges(i) for i in range(3)] + [r.tokenisedTicker(i) for i in range(3)]
  oracle.setAssetSources( addresses, addresses, {"from": timelock}) 

  # Load all into Lending Pool
  theta_A = "0x78b787C1533Acfb84b8C76B7e5CFdfe80231Ea2D" # matic "0xb54240e3F2180A0E14CE405A089f600dc2D8457c"
  theta_stbDebt = "0x8B6Ab2f071b27AC1eEbFfA973D957A767b15b2DB" # matic "0x92ED25161bb90eb0026e579b60B8D96eE3b7A15F"
  theta_varDebt = "0xB19Dd5DAD35af36CF2D80D1A9060f1949b11fCb0" # matic "0x51b89b9e24bc85d6756571032B8bf5660Bf6FbE5"
  theta_100bps_fixed = "0xfAdB757A7BC3031285417d7114EFD58598E21d79" # "0xEdFbbeDdc3CB3271fd60E90E184B151C76Cd88aB"

  reserves = []
  for i in addresses:
      sym = TokenisableRange.at(i).symbol()
      name = TokenisableRange.at(i).name()
      reserves.append( [theta_A, theta_stbDebt, theta_varDebt, 18, theta_100bps_fixed, i, owner.address, NULL, sym, "Roe " + name, "roe"+sym, "Roe variable debt bearing " + name, "vd"+sym, "Roe stable debt bearing " + name, "sd" + sym, ""] )
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  poolAdmin = accounts.at(lpadd.getPoolAdmin(), force=True)
  for i in reserves: config.batchInitReserve([i], {"from": poolAdmin})

  # Enable as collateral
  for i in addresses:
    config.configureReserveAsCollateral(i, 9250, 9500, 10300, {"from": poolAdmin})


# Check balances and price
def test_ranges_values(owner, interface, contracts, lendingPool, usdc, weth, TokenisableRange, prep_ranger, roerouter, liquidityRatio):
  tr, trb, r, rpm = contracts
  poolId = roerouter.getPoolsLength() - 1
  range = TokenisableRange.at(r.tokenisedRanges(1)) # current price at fixed block is 1ETH@1262USDC so price is within 2nd range 1100-1300
  # token  amounts
  usdAmount, ethAmount = liquidityRatio(RANGE_LIMITS[1], RANGE_LIMITS[2])  
  
  with brownie.reverts("RPM: Invalid Range"):
    rpm.farmRange(poolId, NULL, [0, 0], {"from": owner})
    
  with brownie.reverts("RPM: Invalid Amounts"):
    rpm.farmRange(poolId, range, [10], {"from": owner})

  # add false ratio
  with brownie.reverts():
    rpm.farmRange(poolId, range, [1, 1], {"from": owner})

  # direct call unallowed
  from eth_abi import encode_abi
  calldata = encode_abi(['uint', 'uint8', 'address', 'address'], [poolId, 0, owner.address, range.address])
  with brownie.reverts("RPM: Call Unallowed"):
    rpm.executeOperation([], [], [], owner, calldata, {"from": owner})
  
  # Aave: Borrow allowance not enough
  with brownie.reverts('59'):
    rpm.farmRange(poolId, range, [usdAmount, ethAmount], {"from": owner})
    
  interface.ICreditDelegationToken( lendingPool.getReserveData(usdc)[9] ).approveDelegation(rpm, 2**256-1, {"from": owner})
  interface.ICreditDelegationToken( lendingPool.getReserveData(weth)[9] ).approveDelegation(rpm, 2**256-1, {"from": owner})
  rpm.farmRange(poolId, range, [usdAmount, ethAmount], {"from": owner})
  
  print('res', lendingPool.getReserveData(range), lendingPool.getReserveData(range)[9])
  # close range
  liquidity = interface.ERC20(lendingPool.getReserveData(range)[9]).balanceOf(owner)
  #rpm.closeRange(poolId, owner, range, liquidity, {"from": owner})



# Test leveraged farming v2
def test_ranges_values(owner, interface, contracts, lendingPool, usdc, weth, TokenisableRange, prep_ranger, roerouter):
  tr, trb, r, rpm = contracts
  
  from eth_abi import encode_abi
  calldata = encode_abi(['uint', 'uint8', 'address', 'address'], [0, 1, owner.address, WETHUSDC])
  lendingPool.flashLoan(rpm, [USDC, WETH], [1262e6, 1e18], [2,2], owner.address, calldata, 0, {"from": owner})
