import {
  Activity,
  ArrowLeftRight,
  BarChart3,
  LayoutDashboard,
  Network,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Pages that arrive in a later phase render a calm placeholder. */
  phase?: number;
}

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/trade", label: "Trade", icon: ArrowLeftRight },
  { href: "/market", label: "Market", icon: BarChart3 },
  { href: "/grid", label: "Grid", icon: Network },
  { href: "/reputation", label: "Reputation", icon: ShieldCheck },
  { href: "/fairness", label: "Fairness", icon: Scale },
];

export const SECONDARY_NAV: NavItem[] = [{ href: "/status", label: "System status", icon: Activity }];

/** Bottom tab bar shows only the four primary destinations. */
export const MOBILE_NAV = NAV.slice(0, 4);
