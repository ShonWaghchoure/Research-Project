import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/** Default faucet: 100_000 paise = 1000 INR per day. */
const FAUCET_AMOUNT = 100_000n;
/** Minimum stake: 10_000 paise = 100 INR. */
const MIN_STAKE = 10_000n;
/** Withdraw cooldown: 1 day. */
const WITHDRAW_COOLDOWN = 24n * 60n * 60n;
/** Retail tariff: 800 paise/kWh. */
const P_RET_PAISE = 800;

async function main() {
  const [deployer] = await ethers.getSigners();
  const operator = deployer;
  console.log(`Deploying with ${deployer.address} on ${network.name}`);

  const MockINR = await ethers.getContractFactory("MockINR");
  const token = await MockINR.deploy(FAUCET_AMOUNT);
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`MockINR: ${tokenAddress}`);

  const Registry = await ethers.getContractFactory("Registry");
  const registry = await Registry.deploy(
    tokenAddress,
    MIN_STAKE,
    WITHDRAW_COOLDOWN,
    deployer.address,
    operator.address
  );
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();
  console.log(`Registry: ${registryAddress}`);

  const ReputationAnchor = await ethers.getContractFactory("ReputationAnchor");
  const reputation = await ReputationAnchor.deploy(deployer.address, operator.address);
  await reputation.waitForDeployment();
  const reputationAddress = await reputation.getAddress();
  console.log(`ReputationAnchor: ${reputationAddress}`);

  const Settlement = await ethers.getContractFactory("Settlement");
  const settlement = await Settlement.deploy(
    tokenAddress,
    registryAddress,
    P_RET_PAISE,
    deployer.address,
    operator.address
  );
  await settlement.waitForDeployment();
  const settlementAddress = await settlement.getAddress();
  console.log(`Settlement: ${settlementAddress}`);

  const settlementRole = await registry.SETTLEMENT_ROLE();
  await (await registry.grantRole(settlementRole, settlementAddress)).wait();
  console.log("Granted SETTLEMENT_ROLE to Settlement");

  // Keep Ping for Phase 0 smoke compatibility.
  const Ping = await ethers.getContractFactory("Ping");
  const ping = await Ping.deploy();
  await ping.waitForDeployment();
  const pingAddress = await ping.getAddress();
  console.log(`Ping: ${pingAddress}`);

  const networkName = network.name === "hardhat" ? "localhost" : network.name;
  const deploymentsDir = path.join(__dirname, "..", "deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const factories = [
    { name: "MockINR", factory: MockINR, address: tokenAddress },
    { name: "Registry", factory: Registry, address: registryAddress },
    { name: "ReputationAnchor", factory: ReputationAnchor, address: reputationAddress },
    { name: "Settlement", factory: Settlement, address: settlementAddress },
    { name: "Ping", factory: Ping, address: pingAddress },
  ] as const;

  const contracts: Record<string, { address: string; abi: unknown }> = {};
  for (const c of factories) {
    contracts[c.name] = {
      address: c.address,
      abi: JSON.parse(c.factory.interface.formatJson()),
    };
  }

  const deploymentData = {
    network: networkName,
    chainId: network.config.chainId ?? 31337,
    MockINR: tokenAddress,
    Registry: registryAddress,
    ReputationAnchor: reputationAddress,
    Settlement: settlementAddress,
    Ping: pingAddress,
    params: {
      faucetAmount: FAUCET_AMOUNT.toString(),
      minStake: MIN_STAKE.toString(),
      withdrawCooldown: WITHDRAW_COOLDOWN.toString(),
      pRetPaise: P_RET_PAISE,
    },
    contracts,
    updatedAt: new Date().toISOString(),
  };

  const deploymentPath = path.join(deploymentsDir, `${networkName}.json`);
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentData, null, 2));
  console.log(`Wrote deployment info to: ${deploymentPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
