import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`Deploying contracts with account: ${deployer.address} on network: ${network.name}`);

  const PingFactory = await ethers.getContractFactory("Ping");
  const ping = await PingFactory.deploy();
  await ping.waitForDeployment();

  const pingAddress = await ping.getAddress();
  console.log(`Ping contract deployed to: ${pingAddress}`);

  const networkName = network.name === "hardhat" ? "localhost" : network.name;
  const deploymentsDir = path.join(__dirname, "..", "deployments");

  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const deploymentData = {
    network: networkName,
    chainId: network.config.chainId ?? 31337,
    Ping: pingAddress,
    contracts: {
      Ping: {
        address: pingAddress,
        abi: JSON.parse(PingFactory.interface.formatJson()),
      },
    },
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
