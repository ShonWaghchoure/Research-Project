"use client";

import { useCallback, useState } from "react";
import { useAccount, useSignMessage } from "wagmi";
import { useAuth } from "./auth";
import { readableTxError } from "./tx";

/** Sign-In With Ethereum through the connected wallet. */
export function useSiwe() {
  const { address } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const signIn = useAuth((s) => s.signIn);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    if (!address) throw new Error("Connect a wallet first.");
    setBusy(true);
    setError(null);
    try {
      return await signIn(address, (message) => signMessageAsync({ message }));
    } catch (err) {
      const msg = readableTxError(err);
      setError(msg);
      throw new Error(msg);
    } finally {
      setBusy(false);
    }
  }, [address, signIn, signMessageAsync]);

  return { signIn: run, busy, error };
}
