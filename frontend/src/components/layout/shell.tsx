"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { filterNav, MOBILE_NAV, NAV, SECONDARY_NAV, type NavItem } from "./nav";
import { ThemeToggle } from "./theme-toggle";
import { WalletButton } from "./wallet-button";
import { useAuth } from "@/lib/auth";
import { useMarketSocket } from "@/lib/ws";

function NavLink({ item, mobile = false }: { item: NavItem; mobile?: boolean }) {
  const pathname = usePathname();
  const active = pathname === item.href || pathname.startsWith(item.href + "/");
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-1 rounded text-sm transition-colors",
        mobile ? "flex-col justify-center gap-0.5 px-1 py-1 text-xs" : "px-2 py-1",
        active ? "bg-accent-soft font-medium text-text" : "text-text-muted hover:bg-surface-sunken hover:text-text",
      )}
    >
      <Icon className={cn("shrink-0", mobile ? "h-[18px] w-[18px]" : "h-2 w-2")} aria-hidden />
      <span>{item.label}</span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const role = useAuth((s) => s.role);
  const bare = pathname === "/" || pathname.startsWith("/onboarding");
  const socket = useMarketSocket(!bare);
  const primary = filterNav(NAV, role);
  const mobile = filterNav(MOBILE_NAV, role);

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-50 rounded bg-surface-raised px-2 py-1 text-sm">
        Skip to content
      </a>

      {!bare && (
        <aside className="sticky top-0 hidden h-screen w-[208px] shrink-0 flex-col border-r border-border bg-surface-sunken md:flex">
          <Link href="/" className="flex items-center gap-1 px-3 py-3 text-sm font-semibold text-text">
            <span className="inline-block h-[10px] w-[10px] rounded-sm bg-accent" aria-hidden />
            P2P Energy Market
          </Link>
          <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2">
            {primary.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-0.5 px-2 pb-3">
            {SECONDARY_NAV.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
            <div className="mt-1 flex items-center justify-between px-2 text-xs text-text-faint">
              <span className="flex items-center gap-0.5">
                <span
                  aria-hidden
                  className={cn(
                    "inline-block h-[6px] w-[6px] rounded-full",
                    socket === "open" ? "bg-success" : socket === "connecting" ? "bg-warning" : "bg-danger",
                  )}
                />
                {socket === "open" ? "Live" : socket === "connecting" ? "Connecting" : "Offline"}
              </span>
              <ThemeToggle />
            </div>
          </div>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-6 items-center justify-between border-b border-border bg-surface/95 px-2 backdrop-blur md:px-4">
          <Link href="/" className={cn("text-sm font-semibold text-text", !bare && "md:hidden")}>
            P2P Energy Market
          </Link>
          <div className="flex items-center gap-1">
            {bare && <ThemeToggle />}
            <WalletButton />
          </div>
        </header>

        <main id="main" className={cn("mx-auto w-full max-w-content flex-1 px-2 py-3 md:px-4 md:py-4", !bare && "pb-10 md:pb-4")}>
          {children}
        </main>
      </div>

      {!bare && (
        <nav
          aria-label="Primary"
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-border bg-surface-raised md:hidden"
        >
          {mobile.map((item) => (
            <NavLink key={item.href} item={item} mobile />
          ))}
        </nav>
      )}
    </div>
  );
}
