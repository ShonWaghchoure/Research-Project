"use client";

import { useCallback, useEffect, useState } from "react";
import { useAccount, useConnect, useDisconnect } from "wagmi";
import { privateKeyToAccount } from "viem/accounts";
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Wallet,
  Server,
  Database,
  Radio,
  KeyRound,
  BookOpen,
  Shield,
  User,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Hardhat account #0 — demo only (never use on mainnet). */
const DEMO_PK =
  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80" as const;

interface HealthData {
  status: string;
  postgres: string;
  redis: string;
  chain_rpc: string;
  block_number: number | null;
  chain_id: number;
}

interface MeData {
  user_id: number;
  address: string;
  role: string;
  participant: {
    id: number;
    display_name: string | null;
    type: string;
    feeder_node_id: string;
    pv_capacity_kw: number;
    battery_kwh: number;
    active: boolean;
  } | null;
}

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<MeData | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [adminProbe, setAdminProbe] = useState<string | null>(null);

  const { address, isConnected, chain } = useAccount();
  const { connectors, connect } = useConnect();
  const { disconnect } = useDisconnect();

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/health`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data: HealthData = await res.json();
      setHealth(data);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to fetch backend health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const siweLogin = async () => {
    setAuthBusy(true);
    setAuthError(null);
    setAdminProbe(null);
    try {
      const account = privateKeyToAccount(DEMO_PK);
      const nonceRes = await fetch(`${API}/auth/nonce`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: account.address }),
      });
      if (!nonceRes.ok) throw new Error(`nonce failed: ${nonceRes.status}`);
      const { message } = await nonceRes.json();

      const signature = await account.signMessage({ message });

      const verifyRes = await fetch(`${API}/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: account.address,
          message,
          signature,
        }),
      });
      if (!verifyRes.ok) throw new Error(`verify failed: ${verifyRes.status}`);
      const { access_token } = await verifyRes.json();
      setToken(access_token);

      const meRes = await fetch(`${API}/me`, {
        headers: { Authorization: `Bearer ${access_token}` },
      });
      if (!meRes.ok) throw new Error(`me failed: ${meRes.status}`);
      setMe(await meRes.json());

      const adminRes = await fetch(`${API}/admin/config`, {
        headers: { Authorization: `Bearer ${access_token}` },
      });
      if (adminRes.status === 200) {
        const cfg = await adminRes.json();
        const n = Object.keys(cfg.values ?? cfg).length;
        setAdminProbe(`admin OK — ${n} config keys`);
      } else {
        setAdminProbe(`admin → HTTP ${adminRes.status}`);
      }
    } catch (err: unknown) {
      setAuthError(err instanceof Error ? err.message : "SIWE login failed");
      setToken(null);
      setMe(null);
    } finally {
      setAuthBusy(false);
    }
  };

  const logout = () => {
    setToken(null);
    setMe(null);
    setAdminProbe(null);
    setAuthError(null);
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-12">
      <div className="max-w-5xl mx-auto space-y-8">
        <header className="border-b border-slate-800 pb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
              <span className="p-2 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
                ⚡
              </span>
              Fair &amp; Trustworthy P2P Energy Trading
            </h1>
            <p className="text-slate-400 mt-1">
              Phase 6 demo — health, SIWE login, profile &amp; admin config
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={`${API}/docs`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-sm font-medium transition"
            >
              <BookOpen className="w-4 h-4 text-teal-400" />
              API Docs
            </a>
            <button
              onClick={fetchHealth}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-sm font-medium transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
              <StatusRow
                icon={<Database className="w-4 h-4 text-sky-400" />}
                label="PostgreSQL"
                value={health?.postgres}
              />
              <StatusRow
                icon={<Activity className="w-4 h-4 text-rose-400" />}
                label="Redis"
                value={health?.redis}
              />
              <StatusRow
                icon={<Radio className="w-4 h-4 text-teal-400" />}
                label="Chain RPC"
                value={health?.chain_rpc}
              />
              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                <span className="text-slate-400">Block / Chain ID</span>
                <span className="font-mono text-teal-300">
                  {health?.block_number != null ? `#${health.block_number}` : "—"} ·{" "}
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

          <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-sm space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div className="flex items-center gap-2 text-lg font-semibold text-white">
                <KeyRound className="w-5 h-5 text-teal-400" />
                SIWE Login (Phase 6)
              </div>
              {token ? (
                <span className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  JWT
                </span>
              ) : (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-800 text-slate-400">
                  LOGGED OUT
                </span>
              )}
            </div>

            <p className="text-sm text-slate-400">
              Signs a nonce with Hardhat account #0 (admin) — same flow as{" "}
              <code className="text-teal-300/90">scripts/siwe_login.py</code>.
            </p>

            {authError && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm rounded-lg">
                {authError}
              </div>
            )}

            {!token ? (
              <button
                onClick={siweLogin}
                disabled={authBusy}
                className="w-full py-2.5 px-4 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold text-sm transition shadow-lg shadow-teal-500/20 disabled:opacity-50"
              >
                {authBusy ? "Signing…" : "Sign in with Ethereum (demo)"}
              </button>
            ) : (
              <div className="space-y-4">
                <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-slate-400">
                    <User className="w-4 h-4" /> GET /me
                  </div>
                  <p className="font-mono text-teal-300 break-all text-xs">
                    {me?.address}
                  </p>
                  <p>
                    Role: <span className="text-emerald-400 font-medium">{me?.role}</span>
                    {me?.participant && (
                      <>
                        {" "}
                        · {me.participant.display_name} ({me.participant.type}) @{" "}
                        {me.participant.feeder_node_id}
                      </>
                    )}
                  </p>
                  {me?.participant && (
                    <p className="text-slate-400 text-xs">
                      PV {me.participant.pv_capacity_kw} kW · battery{" "}
                      {me.participant.battery_kwh} kWh
                    </p>
                  )}
                </div>

                {adminProbe && (
                  <div className="flex items-start gap-2 p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-sm">
                    <Shield className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                    <span>
                      GET /admin/config → <span className="text-amber-200">{adminProbe}</span>
                    </span>
                  </div>
                )}

                <button
                  onClick={logout}
                  className="w-full py-2.5 px-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 hover:bg-rose-500/20 text-sm font-medium transition"
                >
                  Clear session
                </button>
              </div>
            )}
          </section>

          <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-sm space-y-5 md:col-span-2">
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
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                    Connected Account
                  </label>
                  <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 font-mono text-sm text-teal-300 break-all select-all">
                    {address}
                  </div>
                </div>
                <div className="flex flex-col justify-between gap-3">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 text-sm">
                    <span className="text-slate-400">Network</span>
                    <span className="font-mono text-slate-300">
                      {chain?.name ?? "Hardhat (31337)"}
                    </span>
                  </div>
                  <button
                    onClick={() => disconnect()}
                    className="py-2.5 px-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 hover:bg-rose-500/20 text-sm font-medium transition"
                  >
                    Disconnect Wallet
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <p className="text-sm text-slate-400 flex-1">
                  Optional: connect MetaMask on chain 31337. Full market UI lands in Phase 8.
                </p>
                <div className="flex flex-wrap gap-2">
                  {connectors.map((connector) => (
                    <button
                      key={connector.uid}
                      onClick={() => connect({ connector })}
                      className="py-2.5 px-4 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold text-sm transition shadow-lg shadow-teal-500/20"
                    >
                      {connector.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        <footer className="text-xs text-slate-500 text-center border-t border-slate-900 pt-6 space-y-1">
          <p>
            Live:{" "}
            <a className="text-teal-400/80 hover:underline" href="http://localhost:3000">
              localhost:3000
            </a>{" "}
            · API{" "}
            <a className="text-teal-400/80 hover:underline" href={`${API}/docs`}>
              {API}/docs
            </a>
          </p>
          <p>
            Market trading UI (commit/reveal, dashboard) is Phase 8 — this page demos Phase 6 auth
            + health.
          </p>
        </footer>
      </div>
    </main>
  );
}

function StatusRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value?: string;
}) {
  const ok = value === "ok";
  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
      <span className="text-slate-400 flex items-center gap-2">
        {icon} {label}
      </span>
      <span className={`font-mono ${ok ? "text-emerald-400" : "text-amber-300"}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}
