"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import type { FairnessBaseline } from "./api/types";
import { useAuth } from "./auth";

export const queryKeys = {
  health: ["health"] as const,
  interval: ["interval", "current"] as const,
  priceHistory: ["price-history"] as const,
  orderbook: ["orderbook"] as const,
  positionsMine: ["positions", "mine"] as const,
  trades: (mine = false) => ["trades", mine ? "mine" : "all"] as const,
  reputation: (address: string) => ["reputation", address.toLowerCase()] as const,
  reputationHistory: (address: string) => ["reputation", address.toLowerCase(), "history"] as const,
  reputationProof: (address: string, intervalId: number) =>
    ["reputation", address.toLowerCase(), "proof", intervalId] as const,
  grid: ["grid"] as const,
  fairness: (baseline: FairnessBaseline) => ["fairness", baseline] as const,
};

export const useHealth = () =>
  useQuery({ queryKey: queryKeys.health, queryFn: api.health, refetchInterval: 10_000 });

export const useCurrentInterval = () =>
  useQuery({
    queryKey: queryKeys.interval,
    queryFn: api.intervals.current,
    // Fallback polling when the socket is down.
    refetchInterval: 15_000,
  });

export const usePriceHistory = (limit = 96) =>
  useQuery({ queryKey: [...queryKeys.priceHistory, limit], queryFn: () => api.priceHistory(limit) });

export const useOrderbook = () =>
  useQuery({ queryKey: queryKeys.orderbook, queryFn: api.orderbook, refetchInterval: 15_000 });

export const useMyPositions = () => {
  const token = useAuth((s) => s.token);
  return useQuery({
    queryKey: queryKeys.positionsMine,
    queryFn: api.positions.mine,
    enabled: !!token,
  });
};

export const useTrades = (mine = false, limit = 20) => {
  const token = useAuth((s) => s.token);
  return useQuery({
    queryKey: [...queryKeys.trades(mine), limit],
    queryFn: () => api.trades.list({ mine, limit }),
    enabled: !mine || !!token,
    refetchInterval: 30_000,
  });
};

export const useReputation = (address?: string | null) =>
  useQuery({
    queryKey: queryKeys.reputation(address ?? ""),
    queryFn: () => api.reputation(address as string),
    enabled: !!address,
  });

export const useReputationHistory = (address?: string | null) =>
  useQuery({
    queryKey: queryKeys.reputationHistory(address ?? ""),
    queryFn: () => api.reputationHistory(address as string),
    enabled: !!address,
  });

export const useGridStatus = () =>
  useQuery({ queryKey: queryKeys.grid, queryFn: api.grid, refetchInterval: 30_000 });

export const useFairnessHistory = (baseline: FairnessBaseline = "B3", limit = 96) =>
  useQuery({
    queryKey: [...queryKeys.fairness(baseline), limit],
    queryFn: () => api.fairnessHistory(baseline, limit),
    refetchInterval: 30_000,
  });
