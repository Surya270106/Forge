"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const navigation = [
  { href: "/", label: "Dashboard", index: "01" },
  { href: "/repositories", label: "Repositories", index: "02" },
  { href: "/tasks", label: "Runs", index: "03" },
  { href: "/bench", label: "Bench", index: "04" },
  { href: "/settings/provider", label: "Settings", index: "05" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email: string; name: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [signOutError, setSignOutError] = useState("");
  const isDashboard = pathname === "/";

  useEffect(() => {
    if (pathname?.startsWith("/login")) {
      setLoading(false);
      return;
    }
    localStorage.removeItem("forge_token");
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      if (active) { setAuthError("Workspace sign-in timed out."); setLoading(false); }
      controller.abort();
    }, 5000);
    fetch(`/api/v1/auth/me`, { signal: controller.signal })
      .then((response) => {
        window.clearTimeout(timeoutId);
        if (controller.signal.aborted) throw new Error("Workspace sign-in timed out.");
        if (response.status === 401) { router.push("/login"); return null; }
        if (!response.ok) throw new Error("Workspace sign-in could not be checked.");
        return response.json();
      })
      .then((data) => {
        if (!data) return;
        setUser(data);
        setLoading(false);
      })
      .catch((error) => {
        window.clearTimeout(timeoutId);
        if (active) { setAuthError(controller.signal.aborted ? "Workspace sign-in timed out." : error instanceof Error ? error.message : "Workspace sign-in is unavailable."); setLoading(false); }
      });
    return () => { active = false; window.clearTimeout(timeoutId); controller.abort(); };
  }, [pathname, router]);

  const signOut = async () => {
    setSignOutError("");
    try {
      const response = await fetch(`/api/v1/auth/logout`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("Session revocation failed");
      localStorage.removeItem("forge_org_id");
      router.push("/login");
    } catch {
      setSignOutError("Could not sign out. Please try again.");
    }
  };
  const active = (href: string) =>
    href === "/" ? pathname === "/" : pathname?.startsWith(`/${href.split("/")[1]}`);

  if (pathname?.startsWith("/login")) return <>{children}</>;
  if (authError) return <div className="app-loading app-auth-error" role="alert"><strong>Forge could not check your session.</strong><span>{authError}</span><button type="button" onClick={() => window.location.reload()}>Retry</button></div>;
  if (loading) {
    return (
      <div className="app-loading">
        <span className="loading-orbit" aria-hidden="true" />
        <span>Establishing workspace</span>
      </div>
    );
  }

  return (
    <div className={`app-shell ${isDashboard ? "app-shell-dashboard" : ""}`}>
      <header className="site-header app-header">
        <Link className="brand" href="/" aria-label="Forge workspace home">
          <span className="brand-mark" aria-hidden="true">F</span>
          <strong>Forge</strong>
        </Link>
        <nav className="main-nav app-nav" aria-label="Workspace navigation">
          {navigation.map((item) => (
            <Link href={item.href} className={active(item.href) ? "is-active" : ""} key={item.href}>
              <span>{item.index}</span>{item.label}
            </Link>
          ))}
        </nav>
        <button className="header-source user-control" onClick={() => void signOut()}>
          <span className="user-name">{user?.name || user?.email || "Account"}</span>
          <span aria-hidden="true">Sign out ↗</span>
        </button>
        {signOutError && <span role="alert">{signOutError}</span>}
      </header>
      <main className={isDashboard ? "app-main app-main-dashboard" : "app-main"}>{children}</main>
      <nav className="mobile-nav" aria-label="Mobile workspace navigation">
        {navigation.map((item) => (
          <Link href={item.href} className={active(item.href) ? "is-active" : ""} key={item.href}>
            <span>{item.index}</span>{item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
