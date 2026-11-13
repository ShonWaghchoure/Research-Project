import type { Abi, Address } from "viem";
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

function addr(name: keyof typeof dep.contracts, env: string | undefined): Address {
  return (env && env.length === 42 ? env : dep.contracts[name].address) as Address;
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
