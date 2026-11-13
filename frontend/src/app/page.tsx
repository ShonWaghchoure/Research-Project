"use client";

import { useEffect, useState } from "react";
import { useAccount, useConnect, useDisconnect } from "wagmi";
import { Activity, CheckCircle2, AlertCircle, RefreshCw, Wallet, Server, Database, Radio } from "lucide-react";

interface HealthData {
  status: string;
  postgres: string;
  redis: string;
  chain_rpc: string;
  block_number: number | null;
  chain_id: number;
}

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const { address, isConnected, chain } = useAccount();
  const { connectors, connect } = useConnect();
  const { disconnect } = useDisconnect();

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/health");
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}`);
      }
      const data: HealthData = await res.json();
      setHealth(data);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || "Failed to fetch backend health");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <header className="border-b border-slate-800 pb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
              <span className="p-2 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
                ⚡
              </span>
              Fair &amp; Trustworthy P2P Energy Trading
            </h1>
            <p className="text-slate-400 mt-1">
              Phase 0: Walking Skeleton — Health, Chain RPC &amp; Wallet Verification
            </p>
          </div>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="self-start md:self-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-sm font-medium transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </header>

        {/* Grid layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Backend /health Card */}
          <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-sm space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div className="flex items-center gap-2 text-lg font-semibold text-white">
                <Server className="w-5 h-5 text-teal-400" />
                Backend Status (/health)
              </div>
              {health?.status === "ok" ? (
                <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  HEALTHY
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <AlertCircle className="w-3.5 h-3.5" />
                  {health?.status || "CHECKING"}
                </span>
              )}
            </div>

            {error && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm rounded-lg flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>Backend unreachable: {error}</span>
              </div>
            )}

            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-2">
                  <Database className="w-4 h-4 text-sky-400" /> PostgreSQL
                </span>
                <span className="font-mono text-emerald-400">
                  {health?.postgres ?? "—"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-rose-400" /> Redis Ping
                </span>
                <span className="font-mono text-emerald-400">
                  {health?.redis ?? "—"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-2">
                  <Radio className="w-4 h-4 text-teal-400" /> Current Block Number
                </span>
                <span className="font-mono text-xl font-bold text-teal-300">
                  {health?.block_number !== null && health?.block_number !== undefined
                    ? `#${health.block_number}`
                    : "—"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                <span className="text-slate-400">Configured Chain ID</span>
                <span className="font-mono text-slate-300">
                  {health?.chain_id ?? 31337}
                </span>
              </div>
            </div>

            {lastUpdated && (
              <p className="text-xs text-slate-500 text-right">
                Polled at {lastUpdated.toLocaleTimeString()}
              </p>
            )}
          </section>

          {/* Wagmi Wallet Card */}
          <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-sm space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div className="flex items-center gap-2 text-lg font-semibold text-white">
                <Wallet className="w-5 h-5 text-teal-400" />
                Wallet Connection (wagmi)
              </div>
              {isConnected ? (
                <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  CONNECTED
                </span>
              ) : (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-800 text-slate-400">
                  NOT CONNECTED
                </span>
              )}
            </div>

            {isConnected ? (
              <div className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                    Connected Account
                  </label>
                  <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 font-mono text-sm text-teal-300 break-all select-all">
                    {address}
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 text-sm">
                  <span className="text-slate-400">Network / Chain</span>
                  <span className="font-mono text-slate-300">
                    {chain?.name ?? "Hardhat (31337)"}
                  </span>
                </div>

                <button
                  onClick={() => disconnect()}
                  className="w-full py-2.5 px-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 hover:bg-rose-500/20 text-sm font-medium transition"
                >
                  Disconnect Wallet
                </button>
              </div>
            ) : (
              <div className="space-y-4 text-center py-4">
                <p className="text-sm text-slate-400">
                  Connect your MetaMask or Ethereum browser wallet to verify chain ID 31337.
                </p>

                <div className="space-y-2">
                  {connectors.map((connector) => (
                    <button
                      key={connector.uid}
                      onClick={() => connect({ connector })}
                      className="w-full py-2.5 px-4 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold text-sm transition shadow-lg shadow-teal-500/20"
                    >
                      Connect with {connector.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Footer info */}
        <footer className="text-xs text-slate-500 text-center border-t border-slate-900 pt-6">
          Phase 0 Acceptance: One command starts all (make dev) • GET /health returns ok with block number • Frontend displays block and connected wallet.
        </footer>
      </div>
    </main>
  );
}
