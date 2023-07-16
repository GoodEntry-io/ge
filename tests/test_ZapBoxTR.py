import pytest, brownie
from brownie import network
import math


# CONSTANTS
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
TREASURY="0x50101017adf9D2d06C395471Bc3D6348589c3b97" # random empty
ROUTER="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
ROUTERV3="0xE592427A0AEce92De3Edee1F18E0157C05861564"
# LPAD for btc 0xe7f6F6Cd1Be8313a05e0E38bA97B2A5Dfed7616d - for weth "0x01b76559D512Fa28aCc03630E8954405BcBB1E02"
LENDING_POOL_ADDRESSES_PROVIDER = "0x01b76559D512Fa28aCc03630E8954405BcBB1E02" 
AAVE_WETH = "0x030ba81f1c18d280636f32af80b9aad02cf0854e"
AAVE_USDC = "0xbcca60bb61934080951369a648fb03df4f96263c"
NULL = "0x0000000000000000000000000000000000000000"

# Careful: ticker range now in middle of range, testing ticker
RANGE_LIMITS = [500, 800, 1500, 2500, 5000]

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
def zap(roerouter, ZapBoxTR, weth, owner):
  zap = ZapBoxTR.deploy(roerouter, weth, {"from": owner})
  yield zap

# No isolation when testing uniswap as it will cause reentrancy reverts
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass

  
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
def seed_accounts( weth, usdc, user2, owner, lendingPool, accounts):
  try: 
    aaveUSDC = accounts.at(AAVE_USDC, force=True)
    aaveWETH = accounts.at(AAVE_WETH, force=True)
    
    weth.approve(lendingPool, 2**256-1, {"from": aaveWETH})
    weth.transfer(owner, 10e18, {"from": aaveWETH})
    weth.transfer(user2, 10e18, {"from": aaveWETH})
    lendingPool.deposit(weth, 30e18, owner, 0, {"from": aaveWETH}) 
    #lendingPool.deposit(weth, 30e18, user2, 0, {"from": lotsTokens}) 

    usdc.approve(lendingPool, 2**256-1, {"from": aaveUSDC})
    usdc.transfer(owner, 5e10, {"from": aaveUSDC})
    usdc.transfer(user2, 5e10, {"from": aaveUSDC})
    lendingPool.deposit(usdc, 30e10, owner, 0, {"from": aaveUSDC}) 
    lendingPool.deposit(usdc, 1e10, user2, 0, {"from": aaveUSDC}) 
    
    BEACON="0x00000000219ab540356cBB839Cbe05303d7705Fa"
    beacon = accounts.at(BEACON, force=True)
    beacon.transfer(user2, '10 ether')

  except Exception as e:
    print(e)

  
@pytest.fixture(scope="module", autouse=True)
def contracts(owner, Strings, TickMath, TokenisableRange, UpgradeableBeacon, RangeManager, lendingPool, router, weth, usdc):
  Strings.deploy({"from": owner})
  TickMath.deploy({"from": owner})
  tr = TokenisableRange.deploy({"from": owner})
  trb = UpgradeableBeacon.deploy(tr, {"from": owner})
  r = RangeManager.deploy(lendingPool, usdc, weth, {"from": owner})
  yield tr, trb, r


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


# Check if 2 values are within 0.1%
def nearlyEqual(value0, value1):
  if (value1 == 0): return value1 == value0
  else: return abs (value0-value1) / value1 < 0.001



@pytest.fixture(scope="module", autouse=True)
def prep_ranger(accounts, owner, timelock, lendingPool, weth, usdc, interface, oracle, config, contracts, TokenisableRange, seed_accounts, liquidityRatio):
  tr, trb, r = contracts

  ranges = [ [RANGE_LIMITS[0], RANGE_LIMITS[1]], [RANGE_LIMITS[1], RANGE_LIMITS[2]], [RANGE_LIMITS[2], RANGE_LIMITS[3]] ]
  for i in ranges:
    r.generateRange( i[0]*1e10, i[1]*1e10, i[0], i[1], trb, {"from": owner})

  # Approve rangeManager for initRange
  weth.approve(r, 2**256-1, {"from": owner})
  usdc.approve(r, 2**256-1, {"from": owner})

  # The following lazily fills all the ticks and ranges except the current active one (e.g. 1600-2000)
  # as there's slippage protection, the active Ranger needs to have the correct ratio 
  # - i usually just use uniswap to figure out the ratio i need to deposit, didn't try to calculate

  for i in range(r.getStepListLength()):
    usdAmount, ethAmount = liquidityRatio( ranges[i][0], ranges[i][1])  
    r.initRange(r.tokenisedRanges(i), usdAmount * 100, 100 * ethAmount, {"from": owner})
    usdAmount, ethAmount = liquidityRatio( (ranges[i][0]+ranges[i][1])/2,(ranges[i][0]+ranges[i][1])/2 + 1)
    r.initRange(r.tokenisedTicker(i), usdAmount * 100, 100 * ethAmount, {"from": owner})  
  
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

  for i in reserves: config.batchInitReserve([i], {"from": timelock})

  # Enable as collateral
  for i in addresses:
    config.configureReserveAsCollateral(i, 9250, 9500, 10300, {"from": timelock})
    config.enableBorrowingOnReserve(i, True, {"from": timelock})

  # deposit in lending pool for borrowing
  for i in addresses:
    tr = TokenisableRange.at(i)
    tr.approve(lendingPool, 2**256-1, {"from": owner})
    lendingPool.deposit(tr, tr.balanceOf(owner), owner, 0, {"from": owner})
  

def test_zapIn_token(lendingPool, weth, usdc, user2, interface, zap, roerouter, liquidityRatio, TokenisableRange, contracts):
  tr, trb, r = contracts
  range1 = TokenisableRange.at(r.tokenisedRanges(0))
  print(range1.name() )
  poolId = roerouter.getPoolsLength() - 1
  
  usdAmount, ethAmount = range1.getTokenAmounts(1e18)

  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapIn(poolId, range1, usdAmount, ethAmount, {"from": user2})
  usdc.approve(zap, 2**256-1, {"from": user2})
  weth.approve(zap, 2**256-1, {"from": user2})
 
  beforeBal = interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2)
  zap.zapIn(poolId, range1, usdAmount, ethAmount, {"from": user2})
  assert nearlyEqual( interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2), beforeBal + 1e18 )

  # 2nd ranbge w/ diff token amounts
  range2 = TokenisableRange.at(r.tokenisedRanges(1))
  usdAmount, ethAmount = range2.getTokenAmounts(1e18)
  beforeBal = interface.ERC20( lendingPool.getReserveData(range2)[7] ).balanceOf(user2)
  zap.zapIn(poolId, range2, usdAmount, ethAmount, {"from": user2})
  assert nearlyEqual( interface.ERC20( lendingPool.getReserveData(range2)[7] ).balanceOf(user2), beforeBal + 1e18)



def test_zapIn_ETH(lendingPool, weth, usdc, user2, interface, zap, roerouter, contracts, TokenisableRange):
  tr, trb, r = contracts
  range1 = TokenisableRange.at(r.tokenisedRanges(1))
  print(range1.name())
  poolId = roerouter.getPoolsLength() - 1
  
  usdAmount, ethAmount = range1.getTokenAmounts(1e18)

  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapInETH(poolId, range1, usdc, usdAmount, {"from": user2, "value": ethAmount})
  usdc.approve(zap, 2**256-1, {"from": user2})

  beforeBal = interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2)
  
  with brownie.reverts("ZB: Invalid Token"):
    zap.zapInETH(poolId, range1, ROUTER, usdAmount, {"from": user2, "value": ethAmount})
  zap.zapInETH(poolId, range1, usdc, usdAmount, {"from": user2, "value": ethAmount})
  assert nearlyEqual( interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2), beforeBal + 1e18)

  
  # 2nd ranbge w/ diff token amounts
  range2 = TokenisableRange.at(r.tokenisedRanges(2))
  print(range2.name())
  usdAmount, ethAmount = range2.getTokenAmounts(1e18)
  beforeBal = interface.ERC20( lendingPool.getReserveData(range2)[7] ).balanceOf(user2)
  zap.zapInETH(poolId, range2, usdc, usdAmount, {"from": user2, "value": ethAmount})
  assert nearlyEqual( interface.ERC20( lendingPool.getReserveData(range2)[7] ).balanceOf(user2), beforeBal + 1e18 )



# Zap Out
def test_zapOut(lendingPool, weth, usdc, user2, interface, zap, roerouter, contracts, TokenisableRange):
  tr, trb, r = contracts
  range1 = TokenisableRange.at(r.tokenisedRanges(1))
  print(range1.name())
  poolId = roerouter.getPoolsLength() - 1
  
  usdAmount, ethAmount = range1.getTokenAmounts(1e18)
  usdc.approve(zap, 2**256-1, {"from": user2})
  zap.zapInETH(poolId, range1, usdc, usdAmount, {"from": user2, "value": ethAmount})
  
  # remove half
  roeBal = interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2)
  
  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapOut(poolId, range1, 0, False, {"from":user2})
  interface.ERC20( lendingPool.getReserveData(range1)[7] ).approve(zap, 2**256-1, {"from": user2})
  zap.zapOut(poolId, range1, roeBal / 2, False, {"from":user2})
  assert nearlyEqual( interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2) * 2, roeBal)
  
  # remove all
  usdcBal = usdc.balanceOf(user2)
  zap.zapOut(poolId, range1, 0, True, {"from":user2})
  assert interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user2) == 0
  assert nearlyEqual( usdc.balanceOf(user2), usdcBal + usdAmount )
  



# Zap Out With Permit: Aave aToken support EIP712 permits
@pytest.mark.skip(reason="erroring")
def test_zap_with_permit(chain, lendingPool, weth, usdc, user2, interface, zap, roerouter, contracts, TokenisableRange):
  tr, trb, r = contracts
  range1 = TokenisableRange.at(r.tokenisedRanges(1))
  print(range1.name(), range1.address)
  poolId = roerouter.getPoolsLength() - 1
  user = user2
  
  ethAmount, usdAmount = range1.getTokenAmounts(1e18)
  usdc.approve(zap, 2**256-1, {"from": user2})
  weth.approve(zap, 2**256-1, {"from": user2})
  zap.zapIn(poolId, range1, ethAmount, usdAmount, {"from": user2})
  
  
  ### Deleverage through permit
  # Create permits
  # check: https://github.com/banteg/permit-deposit/blob/master/tests/test_dai_permit.py

  from eth_account import Account, messages
  from eth_account._utils.structured_data.hashing import hash_domain
  from eth_account.messages import encode_structured_data
  from eth_utils import encode_hex


  deadline = chain.time()+3600
  def build_permit(owner, token):
    data = {
      "types": {
        "EIP712Domain": [
          {"name": "name", "type": "string"},
          {"name": "version", "type": "string"},
          {"name": "chainId", "type": "uint256"},
          {"name": "verifyingContract", "type": "address"},
        ],
        "Permit": [
          {"name": "owner", "type": "address"},
          {"name": "spender", "type": "address"},
          {"name": "value", "type": "uint256"},
          {"name": "nonce", "type": "uint256"},
          {"name": "deadline", "type": "uint256"},
        ],
      },
      "primaryType": "Permit",
      "domain": {
        "name": token.name(),
        "version": "1",
        "chainId": 1, #chain.id careful with forking, local chain is 1337 Matic is 137
        "verifyingContract": token.address,
      },
      "message": {
        "owner": owner.address,
        "spender": zap.address,
        "value": 2**256-1,
        "nonce": token._nonces(owner),
        "deadline": deadline,
      },
    }
    #assert encode_hex(hash_domain(data)) == token.DOMAIN_SEPARATOR(), "Domain separator error"
    return encode_structured_data(data)

  permit = build_permit(user, interface.IAToken(lendingPool.getReserveData(range1)[7]) )
  signedPermit = Account.sign_message(permit, user.private_key)
  permitParams = [user.address, zap.address, 2**256-1, deadline, signedPermit.v, signedPermit.r, signedPermit.s]
  
  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapOut(poolId, range1, 0, {"from":user})
  zap.zapOutWithPermit(poolId, range1, 0, permitParams, {"from":user})

  assert interface.ERC20( lendingPool.getReserveData(range1)[7] ).balanceOf(user) == 0
  