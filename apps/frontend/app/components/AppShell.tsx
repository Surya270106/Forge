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
  const [orgs, setOrgs] = useState<any[]>([]); // To be populated later
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Exclude login routes
    if (pathname?.startsWith("/login")) {
      setLoading(false);
      return;
    }

    const token = localStorage.getItem("forge_token");
    if (!token) {
      router.push("/login");
      return;
    }

    // Verify token
    fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/me`, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
      .then(res => {
        if (!res.ok) throw new Error("Unauthorized");
        return res.json();
      })
      .then(data => {
        setUser(data);
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("forge_token");
        router.push("/login");
      });
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
    return <div className="flex h-screen items-center justify-center bg-background"><div className="animate-pulse text-muted">Loading...</div></div>;
  }

  return (
    <div className="flex h-screen w-full flex-col md:flex-row overflow-hidden bg-background">
      <aside className="w-64 border-r border-border bg-surface p-4 flex flex-col hidden md:flex">
        <div className="font-semibold text-xl mb-8 tracking-tight flex items-center gap-2">
          <span className="text-2xl">⚒️</span> Forge
        </div>
        
        <nav className="flex flex-col gap-2 flex-1">
          <Link href="/" className={`px-3 py-2 rounded-md font-medium text-sm flex items-center gap-2 transition-colors ${pathname === "/" ? "bg-accent/10 text-accent" : "text-muted hover:bg-muted-bg"}`}>
            <LayoutDashboard className="w-4 h-4" /> Dashboard
          </Link>
          <Link href="/repositories" className={`px-3 py-2 rounded-md font-medium text-sm flex items-center gap-2 transition-colors ${pathname?.startsWith("/repositories") ? "bg-accent/10 text-accent" : "text-muted hover:bg-muted-bg"}`}>
            <Database className="w-4 h-4" /> Repositories
          </Link>
          <Link href="/tasks" className={`px-3 py-2 rounded-md font-medium text-sm flex items-center gap-2 transition-colors ${pathname?.startsWith("/tasks") ? "bg-accent/10 text-accent" : "text-muted hover:bg-muted-bg"}`}>
            <Activity className="w-4 h-4" /> Runs
          </Link>
          <Link href="/settings" className={`px-3 py-2 rounded-md font-medium text-sm flex items-center gap-2 transition-colors ${pathname?.startsWith("/settings") ? "bg-accent/10 text-accent" : "text-muted hover:bg-muted-bg"}`}>
            <Settings className="w-4 h-4" /> Settings
          </Link>
        </nav>

        {user && (
          <div className="mt-auto border-t border-border pt-4">
            <div className="flex items-center justify-between px-2 py-2">
              <div className="flex flex-col overflow-hidden">
                <span className="text-sm font-medium truncate text-white">{user.name}</span>
                <span className="text-xs text-muted truncate">{user.email}</span>
              </div>
              <button onClick={handleSignOut} className="text-muted hover:text-red-400 p-1 rounded-md transition-colors" title="Sign out">
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </aside>
      
      <main className="flex-1 flex flex-col h-full relative overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
