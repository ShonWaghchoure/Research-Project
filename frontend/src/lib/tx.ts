"use client";

import { useCallback, useState } from "react";
import { BaseError, ContractFunctionRevertedError, UserRejectedRequestError, type Hex } from "viem";
import { usePublicClient, useWalletClient } from "wagmi";
import type { Abi, Address } from "viem";

export type TxStatus = "idle" | "signing" | "pending" | "confirmed" | "failed";

export interface TxState {
  status: TxStatus;
  hash: Hex | null;
  error: string | null;
}

export interface WriteArgs {
  address: Address;
  abi: Abi;
  functionName: string;
  args?: readonly unknown[];
}

/** Turn a viem / wallet error into one sentence a person can act on. */
export function readableTxError(err: unknown): string {
  if (err instanceof BaseError) {
    const rejected = err.walk((e) => e instanceof UserRejectedRequestError);
    if (rejected) return "You declined the signature in your wallet.";
    const reverted = err.walk((e) => e instanceof ContractFunctionRevertedError);
    if (reverted instanceof ContractFunctionRevertedError) {
      const reason = reverted.reason ?? reverted.data?.errorName;
      if (reason) return humaniseRevert(reason);
    }
    const msg = err.shortMessage || err.message;
    if (/insufficient funds/i.test(msg)) return "Not enough ETH for gas on this account.";
    if (/chain .* mismatch|does not match/i.test(msg))
      return "Your wallet is on a different network. Switch to the market network and retry.";
    return humaniseRevert(msg);
  }
  if (err instanceof Error) return humaniseRevert(err.message);
  return "The transaction failed for an unknown reason.";
}

const REVERTS: Record<string, string> = {
  "MockINR: already claimed today": "You already used the faucet today. It refills every UTC day.",
  "Registry: min stake": "Your stake is below the minimum required to register.",
  "Registry: already registered": "This wallet is already registered.",
  "Registry: key taken": "That meter key is already bound to another wallet.",
  "Registry: suspended": "This wallet is suspended and cannot register.",
  "Settlement: commit closed": "The commit window for this interval has closed. Wait for the next one.",
  "Settlement: insufficient escrow": "Your escrow balance is too low for this withdrawal.",
  "Settlement: escrow locked":
    "Escrow is locked until your current position is settled and metered. Try again after this interval.",
  "Settlement: not active":
    "This wallet is not active in the market: finish registration, top up your stake, or contact the operator if suspended.",
  "Registry: cooldown": "Your stake withdrawal is still in its cooldown period.",
  "Registry: not registered": "This wallet is not registered.",
  "Settlement: zero amount": "The amount must be greater than zero.",
  ERC20InsufficientAllowance: "Token approval was too small. Approve the amount and try again.",
  ERC20InsufficientBalance: "Not enough test INR in your wallet. Use the faucet first.",
  EnforcedPause: "The market is paused by the operator.",
};

function humaniseRevert(reason: string): string {
  for (const [key, text] of Object.entries(REVERTS)) if (reason.includes(key)) return text;
  // Strip the contract prefix ("Registry: ...") and keep it short.
  const cleaned = reason.replace(/^[A-Za-z]+:\s*/, "").split("\n")[0];
  return cleaned.length > 140 ? cleaned.slice(0, 140) + "…" : cleaned;
}

/**
 * Shared transaction flow: awaiting signature → pending → confirmed / failed.
 * `run` resolves with the receipt hash or throws a readable error.
 */
export function useTx() {
  const { data: wallet } = useWalletClient();
  const client = usePublicClient();
  const [state, setState] = useState<TxState>({ status: "idle", hash: null, error: null });

  const reset = useCallback(() => setState({ status: "idle", hash: null, error: null }), []);

  const run = useCallback(
    async (write: WriteArgs): Promise<Hex> => {
      if (!wallet || !client) throw new Error("Connect a wallet first.");
      setState({ status: "signing", hash: null, error: null });
      try {
        // Simulate first so a revert surfaces with its reason instead of a gas error.
        const { request } = await client.simulateContract({
          account: wallet.account,
          ...write,
        });
        const hash = await wallet.writeContract(request);
        setState({ status: "pending", hash, error: null });
        const receipt = await client.waitForTransactionReceipt({ hash, confirmations: 1 });
        if (receipt.status !== "success") {
          setState({ status: "failed", hash, error: "The transaction was reverted on chain." });
          throw new Error("The transaction was reverted on chain.");
        }
        setState({ status: "confirmed", hash, error: null });
        return hash;
      } catch (err) {
        const message = readableTxError(err);
        setState((s) => ({ status: "failed", hash: s.hash, error: message }));
        throw new Error(message);
      }
    },
    [wallet, client],
  );

  return { ...state, run, reset };
}
