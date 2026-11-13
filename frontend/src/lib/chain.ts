"use client";

import { useAccount, useReadContracts } from "wagmi";
import type { Address } from "viem";
import { contracts } from "./contracts";

export interface ChainAccount {
  balancePaise: bigint;
  escrowPaise: bigint;
  stakePaise: bigint;
  registered: boolean;
  suspended: boolean;
  claimedFaucetToday: boolean;
}

/** Everything the UI reads from the chain about the connected account, in one batch. */
export function useChainAccount(override?: Address) {
  const { address: connected } = useAccount();
  const address = override ?? connected;

  const query = useReadContracts({
    allowFailure: true,
    contracts: address
      ? [
          { ...contracts.MockINR, functionName: "balanceOf", args: [address] },
          { ...contracts.Settlement, functionName: "escrow", args: [address] },
          { ...contracts.Registry, functionName: "getParticipant", args: [address] },
          { ...contracts.MockINR, functionName: "hasClaimedToday", args: [address] },
        ]
      : [],
    query: { enabled: !!address, refetchInterval: 15_000 },
  });

  const [bal, esc, part, claimed] = query.data ?? [];
  const p = part?.result as
    | { stake: bigint; pendingWithdraw: bigint; withdrawAvailableAt: bigint; meterKeyHash: `0x${string}`; registered: boolean; suspended: boolean }
    | undefined;

  const data: ChainAccount | undefined = query.data
    ? {
        balancePaise: (bal?.result as bigint | undefined) ?? 0n,
        escrowPaise: (esc?.result as bigint | undefined) ?? 0n,
        stakePaise: p?.stake ?? 0n,
        registered: p?.registered ?? false,
        suspended: p?.suspended ?? false,
        claimedFaucetToday: (claimed?.result as boolean | undefined) ?? false,
      }
    : undefined;

  return { ...query, data, address };
}
