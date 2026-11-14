"use client";

import { useAccount, useReadContract, useReadContracts } from "wagmi";
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

const ZERO_HASH = "0x0000000000000000000000000000000000000000000000000000000000000000";

/**
 * The commit hash recorded on chain for (interval, connected wallet), or null if none.
 * The chain is the source of truth for "has this position been committed": after a
 * refresh or navigation the page resumes from here instead of from local state.
 */
export function useOnChainCommit(intervalId?: number | null) {
  const { address } = useAccount();
  const q = useReadContract({
    ...contracts.Settlement,
    functionName: "commits",
    args: intervalId != null && address ? [BigInt(intervalId), address] : undefined,
    query: { enabled: intervalId != null && !!address, refetchInterval: 10_000 },
  });
  const hash = (q.data as `0x${string}` | undefined) ?? undefined;
  return { ...q, commitHash: hash && hash !== ZERO_HASH ? hash : null };
}
