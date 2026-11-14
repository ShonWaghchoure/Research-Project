import { isAddress, type Abi, type Address } from "viem";
import deployments from "@/contracts/localhost.json";

/**
 * Contract addresses and ABIs.
 * `src/contracts/localhost.json` is a snapshot of contracts/deployments/localhost.json
 * refreshed by `npm run sync-contracts`. Environment variables override the addresses
 * so a Sepolia deployment needs no code change.
 */
type Deployment = {
  chainId: number;
  params: { faucetAmount: string; minStake: string; withdrawCooldown: string; pRetPaise: number };
  contracts: Record<string, { address: string; abi: unknown }>;
};

const dep = deployments as unknown as Deployment;

const LOCAL_CHAIN_ID = 31337;
const ACTIVE_CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID ?? LOCAL_CHAIN_ID);

/**
 * On the local chain, addresses default to the deployment snapshot. On any other chain they
 * must be configured explicitly: falling back to the Hardhat addresses on Sepolia would send
 * approvals and deposits to whatever someone else deployed there with the public Hardhat key.
 */
function addr(name: keyof typeof dep.contracts, env: string | undefined): Address {
  if (env) {
    if (!isAddress(env)) throw new Error(`Invalid ${String(name)} address in environment: ${env}`);
    return env as Address;
  }
  if (ACTIVE_CHAIN_ID !== LOCAL_CHAIN_ID || dep.chainId !== LOCAL_CHAIN_ID) {
    throw new Error(
      `Missing NEXT_PUBLIC_${String(name).replace(/([a-z])([A-Z])/g, "$1_$2").toUpperCase()}_ADDRESS for chain ${ACTIVE_CHAIN_ID}`,
    );
  }
  return dep.contracts[name].address as Address;
}

export const contracts = {
  MockINR: {
    address: addr("MockINR", process.env.NEXT_PUBLIC_MOCK_INR_ADDRESS),
    abi: dep.contracts.MockINR.abi as Abi,
  },
  Registry: {
    address: addr("Registry", process.env.NEXT_PUBLIC_REGISTRY_ADDRESS),
    abi: dep.contracts.Registry.abi as Abi,
  },
  Settlement: {
    address: addr("Settlement", process.env.NEXT_PUBLIC_SETTLEMENT_ADDRESS),
    abi: dep.contracts.Settlement.abi as Abi,
  },
  ReputationAnchor: {
    address: addr("ReputationAnchor", process.env.NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS),
    abi: dep.contracts.ReputationAnchor.abi as Abi,
  },
} as const;

export const chainParams = {
  faucetAmountPaise: BigInt(dep.params.faucetAmount),
  minStakePaise: BigInt(dep.params.minStake),
  withdrawCooldownSeconds: Number(dep.params.withdrawCooldown),
  pRetPaise: dep.params.pRetPaise,
};
