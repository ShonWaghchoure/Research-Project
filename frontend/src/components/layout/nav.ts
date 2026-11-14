import {
  Activity,
  ArrowLeftRight,
  BarChart3,
  Crosshair,
  FileSearch,
  LayoutDashboard,
  Network,
  Scale,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** When set, only show for this role. */
  role?: "admin";
}

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/trade", label: "Trade", icon: ArrowLeftRight },
  { href: "/market", label: "Market", icon: BarChart3 },
  { href: "/grid", label: "Grid", icon: Network },
  { href: "/reputation", label: "Reputation", icon: ShieldCheck },
  { href: "/fairness", label: "Fairness", icon: Scale },
  { href: "/attack", label: "Attack lab", icon: Crosshair },
  { href: "/audit", label: "Audit", icon: FileSearch },
  { href: "/admin", label: "Admin", icon: Settings, role: "admin" },
];

export const SECONDARY_NAV: NavItem[] = [{ href: "/status", label: "System status", icon: Activity }];

/** Bottom tab bar shows only the four primary destinations. */
export const MOBILE_NAV = NAV.slice(0, 4);

export function filterNav(items: NavItem[], role: string | null | undefined): NavItem[] {
  return items.filter((item) => !item.role || item.role === role);
}
