"use client";

import { useState } from "react";
import Link from "next/link";
import { useAccount, useConnect, useDisconnect, useSwitchChain } from "wagmi";
import { LogOut, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { CHAIN_ID, DEMO_ACCOUNTS, DEMO_WALLET_ENABLED } from "@/lib/wagmi";
import { useAuth } from "@/lib/auth";
import { shortAddress } from "@/lib/utils";

export function WalletButton() {
  const { address, isConnected, chainId } = useAccount();
  const { connectors, connect, isPending, error } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain, isPending: switching } = useSwitchChain();
  const signOut = useAuth((s) => s.signOut);
  const me = useAuth((s) => s.me);
  const [open, setOpen] = useState(false);

  const wrongNetwork = isConnected && chainId !== CHAIN_ID;
  const injected = connectors.find((c) => c.id === "injected");
  const demos = connectors.filter((c) => c.id.startsWith("demo-"));

  if (isConnected && address) {
    return (
      <div className="flex items-center gap-1">
        {wrongNetwork ? (
          <Button size="sm" variant="danger" loading={switching} onClick={() => switchChain({ chainId: CHAIN_ID })}>
            Switch network
          </Button>
        ) : (
          <Badge tone="neutral" className="hidden sm:inline-flex">
            {me?.participant?.display_name ?? "Connected"}
          </Badge>
        )}
        <span className="num font-mono text-xs text-text-muted" title={address}>
          {shortAddress(address)}
        </span>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Disconnect wallet"
          onClick={() => {
            signOut();
            disconnect();
          }}
        >
          <LogOut className="h-2 w-2" aria-hidden />
        </Button>
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        <Wallet className="h-2 w-2" aria-hidden /> Connect
      </Button>
      <DialogContent title="Connect a wallet" description="Your address is your identity in the market. Nothing is sent until you sign.">
        <div className="flex flex-col gap-1">
          {injected && (
            <Button
              variant="secondary"
              size="lg"
              loading={isPending}
              onClick={() => connect({ connector: injected, chainId: CHAIN_ID }, { onSuccess: () => setOpen(false) })}
            >
              Browser wallet (MetaMask or similar)
            </Button>
          )}
          {DEMO_WALLET_ENABLED && demos.length > 0 && (
            <>
              <p className="mt-1 text-xs text-text-muted">
                No wallet? Use a local demo account. These are Hardhat test accounts and only work on the local chain.
              </p>
              {demos.map((c, i) => (
                <Button
                  key={c.id}
                  variant="secondary"
                  loading={isPending}
                  data-testid={c.id}
                  onClick={() => connect({ connector: c, chainId: CHAIN_ID }, { onSuccess: () => setOpen(false) })}
                >
                  {c.name}{" "}
                  <span className="num font-mono text-xs text-text-muted">{shortAddress(DEMO_ACCOUNTS[i])}</span>
                </Button>
              ))}
            </>
          )}
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error.message.split("\n")[0]}
            </p>
          )}
          <p className="mt-1 text-xs text-text-faint">
            New here? <Link href="/onboarding" className="text-accent underline-offset-2 hover:underline">Start onboarding</Link>.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
