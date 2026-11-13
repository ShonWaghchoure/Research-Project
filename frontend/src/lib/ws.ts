"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WS_URL } from "./api/client";
import type { Interval, Trade, WsMessage } from "./api/types";
import { queryKeys } from "./queries";

export type WsStatus = "connecting" | "open" | "closed";

/**
 * One WebSocket per page, with exponential backoff reconnect.
 * Messages either patch the TanStack Query cache directly (cheap, no refetch)
 * or invalidate the keys they affect.
 */
export function useMarketSocket(enabled = true): WsStatus {
  const qc = useQueryClient();
  const [status, setStatus] = useState<WsStatus>("connecting");
  const attempt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      const ws = new WebSocket(WS_URL);
      socket.current = ws;

      ws.onopen = () => {
        attempt.current = 0;
        setStatus("open");
        // Anything missed while offline.
        qc.invalidateQueries({ queryKey: queryKeys.interval });
        qc.invalidateQueries({ queryKey: queryKeys.trades() });
      };

      ws.onmessage = (ev) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        applyMessage(qc, msg);
      };

      ws.onclose = () => {
        if (disposed) return;
        setStatus("closed");
        const delay = Math.min(30_000, 500 * 2 ** attempt.current) + Math.random() * 250;
        attempt.current += 1;
        timer.current = setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      disposed = true;
      if (timer.current) clearTimeout(timer.current);
      socket.current?.close();
    };
  }, [enabled, qc]);

  return status;
}

type QC = ReturnType<typeof useQueryClient>;

export function applyMessage(qc: QC, msg: WsMessage) {
  switch (msg.channel) {
    case "interval": {
      const data = msg.data as Interval;
      qc.setQueryData<Interval>(queryKeys.interval, data);
      if (data.state === "CLEARING" || data.state === "SETTLED") {
        qc.invalidateQueries({ queryKey: queryKeys.priceHistory });
        qc.invalidateQueries({ queryKey: queryKeys.orderbook });
      }
      if (data.state === "OPEN") {
        qc.invalidateQueries({ queryKey: queryKeys.orderbook });
        qc.invalidateQueries({ queryKey: queryKeys.positionsMine });
      }
      // Fairness rows are appended at METERED.
      if (data.state === "METERED" || data.state === "SETTLED") {
        qc.invalidateQueries({ queryKey: ["fairness"] });
      }
      break;
    }
    case "price": {
      const data = msg.data as { interval_id: number; p_ref_paise: number; sdr: number };
      qc.setQueryData<Interval>(queryKeys.interval, (old) =>
        old && old.id === data.interval_id
          ? { ...old, p_ref_paise: data.p_ref_paise, sdr: data.sdr }
          : old,
      );
      qc.invalidateQueries({ queryKey: queryKeys.priceHistory });
      break;
    }
    case "trades": {
      const trade = msg.data as Trade;
      qc.setQueryData<Trade[]>(queryKeys.trades(), (old) =>
        old ? [trade, ...old.filter((t) => t.id !== trade.id)].slice(0, 100) : old,
      );
      qc.invalidateQueries({ queryKey: queryKeys.trades(true) });
      break;
    }
    case "reputation":
      qc.invalidateQueries({ queryKey: ["reputation"] });
      break;
    case "grid":
      qc.invalidateQueries({ queryKey: queryKeys.grid });
      break;
    case "flags":
      qc.invalidateQueries({ queryKey: ["flags"] });
      break;
  }
}
