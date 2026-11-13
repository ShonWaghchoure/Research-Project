"use client";

import { useEffect, useState } from "react";

/** Read design tokens once so Recharts (which needs concrete colours) stays on-theme. */
export function useChartColors() {
  const [colors, setColors] = useState({
    text: "#5b6472",
    faint: "#6b7380",
    border: "#e1e1dc",
    accent: "#2e6b6e",
    primary: "#1b2a41",
    success: "#3f7d5a",
    warning: "#9a6b1e",
    danger: "#a1433c",
    surface: "#ffffff",
    buy: "#2e6b6e",
    sell: "#9a6b1e",
    band: "#e4eeee",
  });

  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
    setColors({
      text: read("--text-muted", "#5b6472"),
      faint: read("--text-faint", "#6b7380"),
      border: read("--border", "#e1e1dc"),
      accent: read("--accent", "#2e6b6e"),
      primary: read("--primary", "#1b2a41"),
      success: read("--success", "#3f7d5a"),
      warning: read("--warning", "#9a6b1e"),
      danger: read("--danger", "#a1433c"),
      surface: read("--surface-raised", "#ffffff"),
      buy: read("--accent", "#2e6b6e"),
      sell: read("--warning", "#9a6b1e"),
      band: read("--accent-soft", "#e4eeee"),
    });
  }, []);

  return colors;
}

export const P_FIT_PAISE = 300;
export const P_RET_PAISE = 800;
