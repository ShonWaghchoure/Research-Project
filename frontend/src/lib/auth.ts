"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { api, setTokenGetter } from "./api/client";
import type { MeResponse } from "./api/types";

interface AuthState {
  token: string | null;
  address: string | null;
  role: string | null;
  me: MeResponse | null;
  /** Sign-In With Ethereum: nonce → personal_sign → verify → JWT. */
  signIn: (
    address: string,
    signMessage: (message: string) => Promise<string>,
  ) => Promise<MeResponse>;
  refreshMe: () => Promise<MeResponse | null>;
  signOut: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      address: null,
      role: null,
      me: null,

      async signIn(address, signMessage) {
        const { message } = await api.auth.nonce(address);
        const signature = await signMessage(message);
        const tok = await api.auth.verify(address, message, signature);
        set({ token: tok.access_token, address: tok.address, role: tok.role });
        const me = await api.me();
        set({ me });
        return me;
      },

      async refreshMe() {
        if (!get().token) return null;
        try {
          const me = await api.me();
          set({ me });
          return me;
        } catch (err) {
          // Expired or invalid token: drop the session quietly.
          if ((err as { status?: number }).status === 401) get().signOut();
          return null;
        }
      },

      signOut() {
        set({ token: null, address: null, role: null, me: null });
      },
    }),
    {
      name: "ftp2p.session",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ token: s.token, address: s.address, role: s.role, me: s.me }),
      // Restored after mount (see Providers) so the first client render matches the
      // server render, which has no session.
      skipHydration: true,
    },
  ),
);

setTokenGetter(() => useAuth.getState().token);

/** True when the signed-in session belongs to the connected wallet. */
export function useIsSignedIn(connectedAddress?: string | null): boolean {
  const { token, address } = useAuth();
  if (!token || !address) return false;
  if (!connectedAddress) return false;
  return address.toLowerCase() === connectedAddress.toLowerCase();
}

/** True when the signed-in user has the admin role. */
export function useIsAdmin(): boolean {
  const role = useAuth((s) => s.role);
  return role === "admin";
}
