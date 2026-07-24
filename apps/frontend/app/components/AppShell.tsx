'use client';

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { env } from "../../config/env";
import { LogOut, Settings, LayoutDashboard, Database, Activity } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ id: string; email: string; name: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Exclude login routes
    if (pathname?.startsWith("/login")) {
      setLoading(false);
      return;
    }

    const token = localStorage.getItem("forge_token");
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    // Verify token
    fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/me`, {
      headers: {
        "Authorization": `Bearer ${token}`
      },
      signal: controller.signal
    })
      .then(res => {
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then(data => {
        setUser(data);
        setLoading(false);
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        console.error("Auth fetch failed:", err);
        localStorage.removeItem("forge_token");
        window.location.href = "/login";
      });
      
    return () => clearTimeout(timeoutId);
  }, [pathname, router]);

  const handleSignOut = () => {
    localStorage.removeItem("forge_token");
    localStorage.removeItem("forge_org_id");
    router.push("/login");
  };

  if (pathname?.startsWith("/login")) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-pulse text-muted font-mono text-sm tracking-widest uppercase">Loading</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full min-h-screen relative">
      {/* Floating Header */}
      <header className="site-header fixed top-4 right-6 left-6 md:left-[104px] z-30 flex min-h-[68px] items-center justify-between px-6 border border-border/40 rounded-2xl bg-surface/80 backdrop-blur-md shadow-sm">
        <Link href="/" className="flex items-center gap-3" aria-label="Forge AI home">
          <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600 text-white font-bold tracking-tighter" aria-hidden="true">F</span>
          <strong className="font-semibold text-lg tracking-tight">Forge</strong>
        </Link>

        {/* Center area could be used for global search or context */}
        <div className="text-sm font-medium text-slate-500">
          {/* Workspace Context Placeholder */}
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-slate-700 hidden sm:inline-block">{user.name}</span>
              <button 
                onClick={handleSignOut} 
                className="text-slate-400 hover:text-red-500 transition-colors p-1" 
                title="Sign out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Left Navigation Rail */}
      <aside className="fixed left-0 top-0 bottom-0 w-20 flex-col items-center py-6 hidden md:flex z-40 bg-surface/50 border-r border-border/40 backdrop-blur-md">
        <nav className="flex flex-col gap-4 w-full items-center mt-24">
          <Link 
            href="/" 
            title="Dashboard"
            className={`p-3 rounded-xl transition-all duration-200 ${
              pathname === "/" ? "bg-blue-600/10 text-blue-600 shadow-sm" : "text-slate-400 hover:text-blue-500 hover:bg-blue-50/50"
            }`}
          >
            <LayoutDashboard className="w-5 h-5" />
          </Link>
          <Link 
            href="/repositories" 
            title="Repositories"
            className={`p-3 rounded-xl transition-all duration-200 ${
              pathname?.startsWith("/repositories") ? "bg-blue-600/10 text-blue-600 shadow-sm" : "text-slate-400 hover:text-blue-500 hover:bg-blue-50/50"
            }`}
          >
            <Database className="w-5 h-5" />
          </Link>
          <Link 
            href="/tasks" 
            title="Runs"
            className={`p-3 rounded-xl transition-all duration-200 ${
              pathname?.startsWith("/tasks") ? "bg-blue-600/10 text-blue-600 shadow-sm" : "text-slate-400 hover:text-blue-500 hover:bg-blue-50/50"
            }`}
          >
            <Activity className="w-5 h-5" />
          </Link>
          <Link 
            href="/settings/provider" 
            title="Settings"
            className={`p-3 rounded-xl transition-all duration-200 mt-8 ${
              pathname?.startsWith("/settings") ? "bg-blue-600/10 text-blue-600 shadow-sm" : "text-slate-400 hover:text-blue-500 hover:bg-blue-50/50"
            }`}
          >
            <Settings className="w-5 h-5" />
          </Link>
        </nav>
      </aside>
      
      {/* Main Content Area */}
      <main className="flex-1 ml-0 md:ml-20 mt-[100px] relative z-10">
        <div className="max-w-6xl mx-auto p-6 md:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
