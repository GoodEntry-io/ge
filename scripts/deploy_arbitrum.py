from brownie import GeVault, accounts, V3Proxy, TickMath, TokenisableRange, UpgradeableBeacon, chain, RoeRouter, BeaconProxy
import web3

print('Deploying on chain.id', chain.id)
PUBLISH_SOURCE = True if chain.id == 42161 else False
# deploy on Arbitrum
# need `export ARBISCAN_TOKEN=YourToken` to publish sources

#dep = accounts.add(private_key="0x0")
dep = accounts[0]
timelock = accounts.at("0x7433D4158c702Dc6bF0974E0bB4EEA152cfbDd6A", force=True)
TREASURY="0x22Cc3f665ba4C898226353B672c5123c58751692"

WETH="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
USDC="0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"
WBTC="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f"
ARB="0x912CE59144191C1204E64559FE8253a0e49E6548"
GMX="0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a"
SUSHI_ROUTER="0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"

LPAP_ETH = "0x067350E557BCeAeb08806Aacd4AecB701c881c67"
LPAP_GMX = "0xC3d0F06E68daa8807F711C53A4bBA3E63580237c"
LPAP_ARB = "0xDdAe26D8739581227712886730E60eD50becF100"
LPAP_BTC = "0x493149e9043d0FDb2A79d23c27bE213b9fa6D444"
ORACLE = "0x8A4236F5eF6158546C34Bd7BC2908B8106Ab1Ea1"
TR_UPG_BEACON = "0x8a79A356F0F9c13C358d2F68F9eCe606014CDC41"

FR_WETH = "0xC25a7Eca5C1b2D2f184B98aC79459667e258dD6F"
FR_GMX = "0xD6Eaf23738c868dC9cF1B00C737E69Df2737fF22"
FR_ARB = "0x837c2e349681e27DC4285419dA13f8bef4E47326"
FR_BTC = "0x310a1eD78130A71BAB44952F5EA98E8db6dD2Dc1"

ROUTERV2="0x061D66e7392Bb056b771c398543f56F0D9Dd5137"


def deploy_beacon_proxy():
  fullRange = BeaconProxy.deploy(TR_UPG_BEACON, bytes(), {"from": dep}, publish_source=PUBLISH_SOURCE)
  return fullRange.address


def gevaultETH(router, v3proxy_03, v3proxy_005):
  print("Deploying Good Vault ETH-USDC")
  # router entries
  router.addPool(LPAP_ETH, WETH, USDC, SUSHI_ROUTER, {"from":dep}) # LP v2
  router.addPool(LPAP_ETH, WETH, USDC, v3proxy_03, {"from":dep}) # proxy v3 - 0.3%
  router.addPool(LPAP_ETH, WETH, USDC, v3proxy_005, {"from":dep}) # proxy v3 - 0.05%
  
  # DEPLOY
  UNISWAPPOOLV3="0xc31e54c7a869b9fcbecc14363cf510d1c41fa443" # Arb-WETHUSDC-0.05
  POOLID=router.getPoolsLength() - 1
  gevault = GeVault.deploy(TREASURY, router, UNISWAPPOOLV3, POOLID, "GEVault ETH-USDC", "geETHUSDC", WETH, True, FR_WETH, {"from": dep}, publish_source=PUBLISH_SOURCE)
  router.setVault(WETH, USDC, gevault, {"from": dep})
  print("GeVault ETH:", gevault)

  # Add tickers
  gevault.pushTick("0xA4ecECf9b265351A23369A45d9d2c672ac3815d3", {"from": dep}) # 1000
  gevault.pushTick("0x3a9725d0ede934eE81292E6C8EF120A197d42bc9", {"from": dep}) # 1100
  gevault.pushTick("0x06254cE41cB6797eDc77Cd4dA751291c52dC7dDF", {"from": dep}) # 1200
  gevault.pushTick("0x484c9Bc50BD6dE78D2F02D4Ee5C16C681f7C19bf", {"from": dep}) # 1300
  gevault.pushTick("0x018107cCBfc982249930230c476C3C0924956Ce6", {"from": dep}) # 1400
  gevault.pushTick("0xb68162C85fE2020466fa50c07af36e00Ba9F537F", {"from": dep}) # 1500
  gevault.pushTick("0x9D6B29EC56492BE7422ae77C336698DAE73f9781", {"from": dep}) # 1600
  gevault.pushTick("0xA650326776e85F96Ef67249fC9AfcC7c8e8d7424", {"from": dep}) # 1700
  gevault.pushTick("0x5c09C0194FC89CcDAe753f348D1534108F29e90a", {"from": dep}) # 1800
  gevault.pushTick("0x503b1d37CbF6AdEc32c6a2a5542848B5953F6CD8", {"from": dep}) # 1900
  gevault.pushTick("0x84A87d273107db6301d6c5d6667a374ff05427bB", {"from": dep}) # 2000
  gevault.pushTick("0x63CA14963FCadb3DAF2F7d7D18e5f27207547E57", {"from": dep}) # 2100
  gevault.pushTick("0x37Fde229137A50Ab4cAeDc8166749cEa3687a66e", {"from": dep}) # 2200
  gevault.pushTick("0x859bD8D62366050e8CFeE64788d0529807569679", {"from": dep}) # 2300
  gevault.pushTick("0x343985278DA318c64D80a194762d4f1CD2b83683", {"from": dep}) # 2400
  gevault.pushTick("0xd6C554C6b68Ca170FEa6426904B8ffc2d928F1F4", {"from": dep}) # 2500


def gevaultGMX(router, v3proxy_03, v3proxy_005):
  print("Deploying Good Vault GMX-USDC")
  # router entries
  router.addPool(LPAP_GMX, GMX, USDC, SUSHI_ROUTER, {"from":dep}) # LP v2
  router.addPool(LPAP_GMX, GMX, USDC, v3proxy_03, {"from":dep}) # proxy v3 - 0.3%
  router.addPool(LPAP_GMX, GMX, USDC, v3proxy_005, {"from":dep}) # proxy v3 - 0.05%
  
  # DEPLOY
  UNISWAPPOOLV3="0xea263b98314369f2245c7b7e6a9f72e25cb8cded" # Arb-GMXUSDC-0.05
  POOLID=router.getPoolsLength() - 1
  gevault = GeVault.deploy(TREASURY, router, UNISWAPPOOLV3, POOLID, "GEVault GMX-USDC", "geGMXUSDC", WETH, True, FR_GMX, {"from": dep}, publish_source=PUBLISH_SOURCE)
  router.setVault(GMX, USDC, gevault, {"from": dep})
  print("GeVault GMX:", gevault)

  # Add tickers
  gevault.pushTick("0x01BDF7129636B2d98241146f3DB4F58dC41982cE", {"from": dep}) # 20
  gevault.pushTick("0x70f9bBB20b013c679f9550B4dce4e2c8a5674360", {"from": dep}) # 25
  gevault.pushTick("0x0dE58Aad74e85369E6F85244Db33c4B1a22EA8C5", {"from": dep}) # 30
  gevault.pushTick("0x9Ced10d1F30d956AE8a1b23AE82b83344F0e2E2e", {"from": dep}) # 35
  gevault.pushTick("0x166442342edB8D14bc9120b3e639096F344bb2Be", {"from": dep}) # 40
  gevault.pushTick("0xf421A1C9c4C8f38fa22F74e1a2D1d0594f3ba4AF", {"from": dep}) # 45
  gevault.pushTick("0xEa5794107E78B2452988078D2ed9D56622F20dc2", {"from": dep}) # 50
  gevault.pushTick("0xbE8A2b4B7d7F66Def7c24fb1D700dEcF8393cB68", {"from": dep}) # 55
  gevault.pushTick("0x16386d0be48F6E2dBC4B9E37C171b8A19333958F", {"from": dep}) # 60
  gevault.pushTick("0x8D4a912C542Adf6c0C5622381B77b095AA9AEb12", {"from": dep}) # 65
  gevault.pushTick("0x75dCF0dFecAE9735a8B2b577797900C0A0F5541E", {"from": dep}) # 70
  gevault.pushTick("0xCbb37F227EEfC831B68730EB4D04e027a1FDa3C6", {"from": dep}) # 75
  gevault.pushTick("0xC8ABe2082121eB883D2Fd0f00ef01fC1e1F92EB8", {"from": dep}) # 80
  gevault.pushTick("0x6f2Fb257FeAa3EAF42A45Cb333231D53c3B713cA", {"from": dep}) # 85
  gevault.pushTick("0x3a19CB6f63328c9c6fD6CAd24F2f31e0cC6681fB", {"from": dep}) # 90
  gevault.pushTick("0xafDa0E4B3905C72eF195AE5D4c98F958236Cc4E8", {"from": dep}) # 95
  gevault.pushTick("0x25F0D5c60Ff283540B277a0C1153d2522d9d32de", {"from": dep}) # 100
  gevault.pushTick("0x3c30067416CE52132Aa42758c366d57ae70ada29", {"from": dep}) # 105
  gevault.pushTick("0xBe81EF56d2eed48683b5425A1BEC7862f5817431", {"from": dep}) # 110
  gevault.pushTick("0xF5EB66E7c5688B71E520Feb08329E52271B99994", {"from": dep}) # 115


def gevaultARB(router, v3proxy_03, v3proxy_005):
  print("Deploying Good Vault ARB-USDC")
  # router entries
  router.addPool(LPAP_ARB, ARB, USDC, SUSHI_ROUTER, {"from":dep}) # LP v2
  router.addPool(LPAP_ARB, ARB, USDC, v3proxy_03, {"from":dep}) # proxy v3 - 0.3%
  router.addPool(LPAP_ARB, ARB, USDC, v3proxy_005, {"from":dep}) # proxy v3 - 0.05%
  
  # DEPLOY
  UNISWAPPOOLV3="0xcda53b1f66614552f834ceef361a8d12a0b8dad8" # Arb-ARBUSDC-0.05
  POOLID=router.getPoolsLength() - 1
  gevault = GeVault.deploy(TREASURY, router, UNISWAPPOOLV3, POOLID, "GEVault ARB-USDC", "geARBUSDC", WETH, True, FR_ARB, {"from": dep}, publish_source=PUBLISH_SOURCE)
  router.setVault(ARB, USDC, gevault, {"from": dep})
  print("GeVault ARB:", gevault)

  # Add tickers
  gevault.pushTick("0x95fb709322198b1F3174a0ad61DbaC0b40bbe742", {"from": dep}) # 0.5
  gevault.pushTick("0x6fF9816dBaa38016f74995cFA40309966ca01959", {"from": dep}) # 0.6
  gevault.pushTick("0xeAeCC3F2247b8C37FCdc7C33244AefA19AaE1797", {"from": dep}) # 0.7
  gevault.pushTick("0xE1255d346F349405e71841e14a8364D1B813D8B6", {"from": dep}) # 0.8
  gevault.pushTick("0x5db91A5c9741D07F07D823E45fF97cC937dd4773", {"from": dep}) # 0.9
  gevault.pushTick("0xf757bfE018485DD82191e84cAACd1b06aCb8E1C4", {"from": dep}) # 1
  gevault.pushTick("0x574373cbB4De913E43E54eC47173358799b1Ce19", {"from": dep}) # 1.1
  gevault.pushTick("0x093650AC482c13CA72Fecc29A1A120476A4fbFdE", {"from": dep}) # 1.2
  gevault.pushTick("0x593E8e0Fb96Fa5707bd7F1D61409331FD5414246", {"from": dep}) # 1.3
  gevault.pushTick("0x20814df302Bf89E6882C2Ff4c0f3b4ACc7a7bbe4", {"from": dep}) # 1.4
  gevault.pushTick("0x352ed8e7E0C91C91F289dED7187fD0cd95b0953F", {"from": dep}) # 1.5
  gevault.pushTick("0x0c797B3728C6A0eCD99CA9E236c63dC5AF7C50cA", {"from": dep}) # 1.6
  gevault.pushTick("0x41cD8fC25FDDcBeBD04d251f2880D5df1486d2A6", {"from": dep}) # 1.7
  gevault.pushTick("0x21b03521582c797d84adCF06912279A1C315477e", {"from": dep}) # 1.8
  gevault.pushTick("0x76008C50fe6F69F94D3e7d2832bb35172FDcD629", {"from": dep}) # 1.9
  gevault.pushTick("0xb124a00Fd8c25578A78a8913224D914788892ffD", {"from": dep}) # 2


def gevaultBTC(router, v3proxy_03, v3proxy_005):
  print("Deploying Good Vault BTC-USDC")
  # router entries
  router.addPool(LPAP_BTC, WBTC, USDC, v3proxy_03, {"from":dep}) # proxy v3 - 0.3%
  router.addPool(LPAP_BTC, WBTC, USDC, v3proxy_005, {"from":dep}) # proxy v3 - 0.05%
  
  # DEPLOY
  UNISWAPPOOLV3="0xac70bd92f89e6739b3a08db9b6081a923912f73d" # Arb-BTCUSDC-0.05
  POOLID=router.getPoolsLength() - 1
  gevault = GeVault.deploy(TREASURY, router, UNISWAPPOOLV3, POOLID, "GEVault BTC-USDC", "geBTCUSDC", WETH, True, FR_BTC, {"from": dep}, publish_source=PUBLISH_SOURCE)
  router.setVault(WBTC, USDC, gevault, {"from": dep})
  print("GeVault BTC:", gevault)

  # Add tickers
  gevault.pushTick("0x24b019239a87a6AA128793B3A2Cc48be29B798f4", {"from": dep}) # 20k
  gevault.pushTick("0x6E49D07202888c7d2A8685540B5911B220f81112", {"from": dep}) # 21k
  gevault.pushTick("0x6D624B5e6929aaCeC6E0EAE5c3576744627948c2", {"from": dep}) # 22k
  gevault.pushTick("0x3d3320CAdAC5082610c7cc88b4ba16ae78465876", {"from": dep}) # 23k
  gevault.pushTick("0xdcbb50c18A3D1Cde3c2d31361b9a0a7862eE16B4", {"from": dep}) # 24k
  gevault.pushTick("0x1Ee660d2A37e4D7bAb9De74f6B33b0FE1e28386E", {"from": dep}) # 25k
  gevault.pushTick("0x65B894266AB1dc89155F8ab693ba46EaeEfa5006", {"from": dep}) # 26k
  gevault.pushTick("0x1e722F33eA399F4aE46b2862ab86C23AE55293B2", {"from": dep}) # 27k
  gevault.pushTick("0xe5E981AB35Dd6D5d136E8bCE02f8ef9135ab2E5d", {"from": dep}) # 28k
  gevault.pushTick("0xcD52675E3a2b82cf9D5E4B5e438E56f90Ad5e7C0", {"from": dep}) # 29k
  gevault.pushTick("0x6E4B9534CA7804DbDF0f41bA82D2CD19bC70AE94", {"from": dep}) # 30k
  gevault.pushTick("0x37a16AaA5Adf758cAe6214436fC8fBf62A6904b5", {"from": dep}) # 31k
  gevault.pushTick("0x5Cb917A9DE0E974a22af60235DbBcdCDfAB0f92A", {"from": dep}) # 32k
  gevault.pushTick("0x246Ea45c63770deb26f3061bF38fC163A1b19B07", {"from": dep}) # 33k
  gevault.pushTick("0xe517bB703e9bB15a1CF73672404ea1faABD9E413", {"from": dep}) # 34k
  gevault.pushTick("0x3b22Bee5BCa7E18AC23C98453546E50F765E7415", {"from": dep}) # 35k
  gevault.pushTick("0x648cA7c6b3C3aF3364aef00e1b85564Eb5Dd0DbA", {"from": dep}) # 36k
  gevault.pushTick("0xb652404899313897aEBfb97382A83106C885A9a8", {"from": dep}) # 37k
  gevault.pushTick("0xa5b14eBD518771A3BC90efDc6aaA70A0aFcF0eFb", {"from": dep}) # 38k
  gevault.pushTick("0xc054F46861289050cc5530792FF55996E2c48226", {"from": dep}) # 39k
  gevault.pushTick("0xa5Ce0E4A2A63b38F01Af26f84D4B5966d9246aBd", {"from": dep}) # 40k


def deploy_TR():
  tickmath = TickMath.deploy({"from": dep}, publish_source=PUBLISH_SOURCE)
  tr = TokenisableRange.deploy({"from": dep}, publish_source=PUBLISH_SOURCE)
  #trb = UpgradeableBeacon.at(TR_UPG_BEACON)
  #trb.upgradeTo(tr2, {"from": timelock})
  return tr
  

def deploy_router2():
  #router = RoeRouter.deploy(TREASURY, {"from": dep}, publish_source=PUBLISH_SOURCE)
  router = RoeRouter.at(ROUTERV2)
  print('Router:', router)
  return router


def deploy_v3proxy(feeTier):
  print('Deploy V3 proxy', feeTier)
  # addresses from https://docs.uniswap.org/contracts/v3/reference/deployments
  QUOTER = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
  SWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
  proxy = V3Proxy.deploy(SWAP_ROUTER, QUOTER, feeTier, {"from": dep}, publish_source=PUBLISH_SOURCE)
  print("ProxyV3", feeTier, "%", proxy)
  return proxy


def main():
  #v3proxy_03 = deploy_v3proxy(3000) # 0.3% v3 pool
  v3proxy_03 = V3Proxy.at("0x59Db3FBf181d129b3BD94B9f5209Afd0A9B39671")
  #v3proxy_005 = deploy_v3proxy(500) # 0.05% v3 pool
  v3proxy_005 = V3Proxy.at("0x40f785d85B89a565521952D3D8Ae731A6ea40126")
  #v3proxy_1 = deploy_v3proxy(10000) # 1% v3 pool
  router = deploy_router2()
  #deploy_TR()
  
  gevaultETH(router, v3proxy_03, v3proxy_005)
  gevaultGMX(router, v3proxy_03, v3proxy_005)
  gevaultARB(router, v3proxy_03, v3proxy_005)
  gevaultBTC(router, v3proxy_03, v3proxy_005)