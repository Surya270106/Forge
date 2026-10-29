"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const navigation = [
  { href: "/", label: "Dashboard", index: "01" },
  { href: "/repositories", label: "Repositories", index: "02" },
  { href: "/tasks", label: "Runs", index: "03" },
  { href: "/settings/provider", label: "Settings", index: "04" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email: string; name: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [signOutError, setSignOutError] = useState("");
  const isDashboard = pathname === "/";

  useEffect(() => {
    if (pathname?.startsWith("/login")) {
      setLoading(false);
      return;
    }
    localStorage.removeItem("forge_token");
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);
    fetch(`/api/v1/auth/me`, { signal: controller.signal })
      .then((response) => {
        window.clearTimeout(timeoutId);
        if (!response.ok) throw new Error("Unauthorized");
        return response.json();
      })
      .then((data) => {
        setUser(data);
        setLoading(false);
      })
      .catch((error) => {
        window.clearTimeout(timeoutId);
        console.error("Auth fetch failed:", error);
        router.push("/login");
      });
    return () => window.clearTimeout(timeoutId);
  }, [pathname, router]);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      const progress = isDashboard
        ? Math.min(Math.max(window.scrollY / (Math.max(window.innerHeight, 1) * 0.9), 0), 1)
        : 0;
      document.documentElement.style.setProperty(
        "--blob-page-opacity",
        String(isDashboard ? 1 - progress * 0.78 : 0.2),
      );
      frame = 0;
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.documentElement.style.removeProperty("--blob-page-opacity");
    };
  }, [isDashboard]);

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
