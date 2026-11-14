import { createConfig, http, cookieStorage, createStorage } from "wagmi";
import { hardhat, sepolia } from "wagmi/chains";
// From @wagmi/core, not wagmi/connectors: the latter bundles every wallet SDK.
import { injected, mock } from "@wagmi/core";
import type { Address } from "viem";

export type SupportedChainId = typeof hardhat.id | typeof sepolia.id;
export const CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID ?? 31337) as SupportedChainId;
export const RPC_URL = process.env.NEXT_PUBLIC_RPC_URL ?? "http://127.0.0.1:8545";

/**
 * Demo accounts: Hardhat's default unlocked accounts (never used on a public network).
 * Index 0 is the operator / admin; the UI offers 1 to 5 for people trying the app without
 * a browser wallet. Only enabled on the local chain.
 */
export const DEMO_ACCOUNTS: Address[] = [
  "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
  "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
  "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
  "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
];

/**
 * Demo wallets sign with Hardhat's publicly known keys, so they must never appear on a
 * public site. Development builds (`next dev`, Playwright, make demo) enable them on the
 * local chain; a production build needs an explicit NEXT_PUBLIC_ENABLE_DEMO_WALLET=true,
 * so forgetting to set NEXT_PUBLIC_CHAIN_ID (which defaults to 31337) cannot turn them on.
 */
export const DEMO_WALLET_ENABLED =
  CHAIN_ID === hardhat.id &&
  process.env.NEXT_PUBLIC_DISABLE_DEMO_WALLET !== "true" &&
  (process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_ENABLE_DEMO_WALLET === "true");

export const chains = [hardhat, sepolia] as const;

/**
 * One connector per demo account so the picker can choose a specific address.
 * The mock connector forwards personal_sign and eth_sendTransaction to the node,
 * where Hardhat's default accounts are unlocked.
 */
function demoConnector(account: Address, index: number) {
  const base = mock({ accounts: [account], features: { reconnect: true } });
  const id = `demo-${index}`;
  const flag = `${id}.connected`;
  return (params: Parameters<typeof base>[0]) => {
    const c = base(params);
    const storage = params.storage;
    return {
      ...c,
      id,
      name: `Demo account ${index + 1}`,
      connect: async function (this: unknown, args?: Parameters<typeof c.connect>[0]) {
        const result = await c.connect.call(this as never, args);
        await storage?.setItem(flag, true);
        return result;
      } as typeof c.connect,
      async disconnect() {
        await storage?.removeItem(flag);
        return c.disconnect.call(this);
      },
      // The mock connector forwards eth_accounts to the node, and Hardhat answers with
      // all 20 unlocked accounts, operator first. Without this pin every demo account
      // would sign and send as the operator.
      async getAccounts() {
        return [account];
      },
      // The base connector keeps "connected" in memory, so after a page refresh it
      // reports unauthorised and wagmi drops the restored session. wagmi asks every
      // connector on load, so authorise only the one this browser connected and has
      // not disconnected since.
      async isAuthorized() {
        return !!(await storage?.getItem(flag));
      },
      async getProvider(...args: Parameters<typeof c.getProvider>) {
        const provider = await c.getProvider(...args);
        return {
          ...provider,
          request: async (req: { method: string; params?: unknown }) =>
            req.method === "eth_accounts" || req.method === "eth_requestAccounts"
              ? [account]
              : provider.request(req as never),
        } as typeof provider;
      },
    };
  };
}

export const DEMO_CONNECTOR_ID = (index: number) => `demo-${index}`;

export const config = createConfig({
  chains,
  connectors: [
    injected({ shimDisconnect: true }),
    ...(DEMO_WALLET_ENABLED ? DEMO_ACCOUNTS.slice(0, 3).map((a, i) => demoConnector(a, i)) : []),
  ],
  transports: {
    [hardhat.id]: http(RPC_URL),
    [sepolia.id]: http(process.env.NEXT_PUBLIC_SEPOLIA_RPC_URL),
  },
  ssr: true,
  storage: createStorage({ storage: cookieStorage }),
});

declare module "wagmi" {
  interface Register {
    config: typeof config;
  }
}
