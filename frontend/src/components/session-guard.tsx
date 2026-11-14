"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAccount } from "wagmi";
import { useAuth } from "@/lib/auth";

/**
 * Keeps the signed-in session bound to the connected wallet. When the wallet changes
 * (e.g. switching accounts in MetaMask) or disconnects, the old JWT is dropped and every
 * cached query is cleared, so one account's positions, trades or admin access never carry
 * over to another. While wagmi is still reconnecting after a page load it does nothing,
 * so a refresh does not sign the user out.
 */
export function SessionGuard() {
  const { address, status } = useAccount();
  const sessionAddress = useAuth((s) => s.address);
  const signOut = useAuth((s) => s.signOut);
  const qc = useQueryClient();

  useEffect(() => {
    if (!sessionAddress) return;
    if (status === "connecting" || status === "reconnecting") return;
    const mismatch = status === "disconnected" || !address || address.toLowerCase() !== sessionAddress.toLowerCase();
    if (mismatch) {
      signOut();
      qc.clear();
    }
  }, [address, status, sessionAddress, signOut, qc]);

  return null;
}
