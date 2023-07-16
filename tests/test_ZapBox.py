import pytest, brownie, math


# CONSTANTS
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WETHUSDC = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
TREASURY="0x50101017adf9D2d06C395471Bc3D6348589c3b97" # random empty
ROUTER="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
LENDING_POOL_ADDRESSES_PROVIDER = "0x01b76559D512Fa28aCc03630E8954405BcBB1E02"

LOTS_LP = "0x9e5405df8a23fa331b8e9c00f39e9b39860bfee4"
AAVE_WETH = "0x030ba81f1c18d280636f32af80b9aad02cf0854e"
AAVE_USDC = "0xbcca60bb61934080951369a648fb03df4f96263c"

@pytest.fixture(scope="module", autouse=True)
def weth(interface, accounts):
  weth = interface.ERC20(WETH)
  yield weth

@pytest.fixture(scope="module", autouse=True)
def usdc(interface, accounts):
  usdc  = interface.ERC20(USDC)
  yield usdc

@pytest.fixture(scope="module", autouse=True)
def wethusdc(interface, owner, accounts):
  wethusdc = interface.IUniswapV2Pair(WETHUSDC)
  yield wethusdc


@pytest.fixture(scope="module", autouse=True)
def router(interface):
  router = interface.IUniswapV2Router02(ROUTER)
  yield router
  
@pytest.fixture(scope="module", autouse=True)
def lendingPool(interface, accounts):
  lpadd = interface.ILendingPoolAddressesProvider(LENDING_POOL_ADDRESSES_PROVIDER)
  config = interface.ILendingPoolConfigurator(lpadd.getLendingPoolConfigurator());
  lendingPool = interface.ILendingPool(lpadd.getLendingPool())
  yield lendingPool

@pytest.fixture(scope="module", autouse=True)
def roerouter(RoeRouter, owner):
  roerouter = RoeRouter.deploy(TREASURY, {"from": owner})
  roerouter.addPool(LENDING_POOL_ADDRESSES_PROVIDER, USDC, WETH, ROUTER, {"from": owner})
  yield roerouter
 
@pytest.fixture(scope="module", autouse=True)
def zap(roerouter, ZapBox, owner):
  zap = ZapBox.deploy(roerouter, {"from": owner})
  yield zap


# Call to seed accounts before isolation tests
@pytest.fixture(scope="module", autouse=True)
def seed_accounts( weth, usdc, wethusdc, owner, user, user2, lendingPool, accounts, ):
  try: 
    aaveUSDC = accounts.at(AAVE_USDC, force=True)
    aaveWETH = accounts.at(AAVE_WETH, force=True)
    
    weth.transfer(user, 1e20, {"from": aaveWETH})
    weth.transfer(user2, 1e20, {"from": aaveWETH})
    usdc.transfer(user, 1e10, {"from": aaveUSDC})
    usdc.transfer(user2, 1e10, {"from": aaveUSDC})
  except:
    pass


# No isolation when testing uniswap as it will cause reentrancy reverts
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


def test_zapIn_token(accounts, chain, lendingPool, wethusdc, weth, usdc, user, interface, router, zap, roerouter):
  poolId = roerouter.getPoolsLength() - 1

  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapIn(poolId, usdc, 1e6, weth, 1e16, {"from": user})
  usdc.approve(zap, 2**256-1, {"from": user})
  weth.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amount1 = amount0 / res0 * res1

  expectedLP = amount0 * wethusdc.totalSupply() / res0
  
  with brownie.reverts("ZB: Zero Amount"): zap.zapIn(poolId, usdc, 0, weth, amount1, {"from": user})
  with brownie.reverts("ZB: Zero Amount"): zap.zapIn(poolId, usdc, amount0, weth, 0, {"from": user})
 
  zap.zapIn(poolId, usdc, amount0, weth, amount1, {"from": user})
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  print('theory', expectedLP, roeBal)
  assert roeBal == math.floor(expectedLP)


def test_zapIn_singleAsset(accounts, chain, lendingPool, wethusdc, weth, usdc, user, interface, router, zap, roerouter):
  poolId = roerouter.getPoolsLength() - 1
  
  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapInSingleAsset(poolId, usdc, 1e6, weth, 1, {"from": user})
  usdc.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amount1 = amount0 / res0 * res1
  # a swap will be made to balance the tokens so it's hard to know what exactly will be the result
  # smth like amount0 * wethusdc.totalSupply() / res0 / 2 /1.003  minus a little excess for swap impact, so we expect at least expectedLP / 2 / 1.004
  expectedLP = amount0 * wethusdc.totalSupply() / res0
  
  with brownie.reverts("ZB: Zero Amount"): zap.zapInSingleAsset(poolId, usdc, 0, weth, amount1, {"from": user})
  zap.zapInSingleAsset(poolId, usdc, amount0, weth, amount1/3, {"from": user})
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  print('theory', expectedLP, roeBal)
  assert roeBal > math.floor(expectedLP / 2.008)


def test_zapIn_ETH(accounts, chain, lendingPool, wethusdc, weth, usdc, user, interface, router, zap, roerouter):
  poolId = roerouter.getPoolsLength() - 1
  usdc.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amountEth = amount0 / res0 * res1
  expectedLP = amount0 * wethusdc.totalSupply() / res0
  
  with brownie.reverts("ZB: Zero Amount"): zap.zapInETH(poolId, usdc, 0, {"from": user, "value": amountEth})
  with brownie.reverts("ZB: Zero Amount"): zap.zapInETH(poolId, usdc, amount0, {"from": user, "value": 0})
  zap.zapInETH(poolId, usdc, amount0, {"from": user, "value": amountEth})
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  assert roeBal == math.floor(expectedLP)
  tx = zap.zapInETH(poolId, usdc, amount0, {"from": user, "value": amountEth })


def test_zapIn_singleAsset_ETH(accounts, chain, lendingPool, wethusdc, weth, usdc, user, interface, router, zap, roerouter):
  poolId = roerouter.getPoolsLength() - 1
  usdc.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amountEth = amount0 / res0 * res1
  # a swap will be made to balance the tokens so it's hard to know what exactly will be the result
  # smth like amount0 * wethusdc.totalSupply() / res0 / 2 /1.003  minus a little excess for swap impact, so we expect at least expectedLP / 2 / 1.004
  expectedLP = amount0 * wethusdc.totalSupply() / res0
  
  with brownie.reverts("ZB: Zero Amount"): zap.zapInSingleAssetETH(poolId,  usdc, amount0, {"from": user, "value": 0})
  zap.zapInSingleAssetETH(poolId, usdc, amount0/3, {"from": user, "value": amountEth})
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  assert roeBal > math.floor(expectedLP / 2.008)
  # second test for testing if->cleanup 2nd branch
  zap.zapInSingleAssetETH(poolId, usdc, amount0/3, {"from": user, "value": amountEth + 5e11})


# Zap Out
def test_zapOut(accounts, chain, lendingPool, wethusdc, weth, usdc, user, interface, router, zap, roerouter):
  poolId = roerouter.getPoolsLength() - 1
  usdc.approve(zap, 2**256-1, {"from": user})
  weth.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amount1 = amount0 / res0 * res1
  expectedLP = amount0 * wethusdc.totalSupply() / res0

  # Get reserves: token0 is USDC and token1 is WETH, based on lexicography
  zap.zapIn(poolId,  usdc, amount0, weth, amount1, {"from": user})
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  print('theory', expectedLP, roeBal)
  assert roeBal == math.floor(expectedLP)
  
  print('token debt',interface.ERC20( lendingPool.getReserveData(wethusdc)[9] ).totalSupply()  )
  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapOut(poolId, wethusdc, 1e6, {"from":user})
  interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).approve(zap, 2**256-1, {"from":user})
  
  # try to remove a little
  roeBal = interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user)
  # there is some ongoing debt so esp. in coverage mode, between the time we check the balance and the check time there will be interest paid
  # because of that the difference could sometimes increase by up to 340 
  zap.zapOut(poolId, wethusdc, 1e6, {"from":user})
  assert abs( interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user) + 1e6 - roeBal ) <= 350 # should be equal or 1 unit diff from rounding err
  # remove remaining
  zap.zapOut(poolId, wethusdc, 0, {"from":user})
  assert interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user) == 0



# Zap Out With Permit: Aave aToken support EIP712 permits
def test_zap_with_permit(accounts, chain, lendingPool, wethusdc, weth, usdc, user, user2, interface, router, zap, owner,  roerouter):
  poolId = roerouter.getPoolsLength() - 1
  user = user2 # need an account with private key available for signing the permit

  # Create a position
  usdc.approve(zap, 2**256-1, {"from": user})
  weth.approve(zap, 2**256-1, {"from": user})

  res0, res1, ts = wethusdc.getReserves()
  amount0 = 10e6
  amount1 = amount0 / res0 * res1
  zap.zapIn(poolId, usdc, amount0, weth, amount1, {"from": user})
  
  
  
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

  permit = build_permit(user, interface.IAToken(lendingPool.getReserveData(wethusdc)[7]) )
  signedPermit = Account.sign_message(permit, user.private_key)
  permitParams = [user.address, zap.address, 2**256-1, deadline, signedPermit.v, signedPermit.r, signedPermit.s]
  
  with brownie.reverts("ERC20: transfer amount exceeds allowance"): zap.zapOut(poolId, wethusdc, 0, {"from":user})
  zap.zapOutWithPermit(poolId, wethusdc, 0, permitParams, {"from":user})
  
  assert interface.ERC20( lendingPool.getReserveData(wethusdc)[7] ).balanceOf(user) == 0


def test_cleanupEth(Test_ZapBox, roerouter, ZapBox, owner):
  test = Test_ZapBox.deploy(roerouter, {"from": owner})
  # send a bit of ETH to the contract
  from brownie import web3
  web3.eth.send_transaction({"from": owner.address, "to": test.address, "value": 1000000000})  
  assert test.balance() == 1e9
  # should succeed in cleaning even if no Eth present
  test.test_cleanupEth()
  assert test.balance() == 0