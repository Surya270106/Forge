'use client';

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { env } from "../../config/env";
import { LogOut, Settings, LayoutDashboard, Database, Activity, PanelLeftClose, PanelLeftOpen, User, ChevronDown } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ id: string; email: string; name: string } | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Navigation expansion state
  const [navExpanded, setNavExpanded] = useState(true);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  useEffect(() => {
    // Load preference from local storage
    const storedNavState = localStorage.getItem("forge_nav_expanded");
    if (storedNavState !== null) {
      setNavExpanded(storedNavState === "true");
    }

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

    fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/me`, {
      headers: { "Authorization": `Bearer ${token}` },
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

  const toggleNav = () => {
    const newState = !navExpanded;
    setNavExpanded(newState);
    localStorage.setItem("forge_nav_expanded", String(newState));
  };

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

  const navItems = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Repositories", href: "/repositories", icon: Database },
    { name: "Runs", href: "/tasks", icon: Activity },
    { name: "Settings", href: "/settings/provider", icon: Settings, bottom: true }
  ];

  const sidebarWidth = navExpanded ? "w-[220px]" : "w-[72px]";

  return (
    <div className="flex flex-col w-full min-h-screen relative">
      {/* Floating Header */}
      <header className={`site-header fixed top-4 right-4 md:right-8 lg:right-10 z-30 flex min-h-[68px] items-center justify-between px-6 border border-forge-line rounded-2xl bg-surface/90 backdrop-blur-md shadow-forge transition-all duration-300 ease-forge left-4 md:left-[104px] ${navExpanded ? "md:left-[252px]" : "md:left-[104px]"}`}>
        <Link href="/" className="flex items-center gap-3" aria-label="Forge AI home">
          <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600 text-white font-bold tracking-tighter shadow-sm" aria-hidden="true">F</span>
          <strong className="font-semibold text-lg tracking-tight hidden sm:block">Forge</strong>
        </Link>

        <div className="text-sm font-medium text-slate-500">
          {/* Global search or context placeholder */}
        </div>

        <div className="flex items-center gap-4 relative">
          {user && (
            <div className="relative">
              <button 
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 hover:bg-slate-50 p-1.5 pr-2 rounded-xl border border-transparent hover:border-slate-200 transition-all duration-200"
              >
                <div className="w-8 h-8 bg-gradient-to-tr from-blue-600 to-indigo-500 text-white rounded-lg flex items-center justify-center font-medium shadow-sm">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <span className="text-sm font-medium text-slate-700 hidden sm:inline-block px-1">{user.name}</span>
                <ChevronDown className="w-4 h-4 text-slate-400 hidden sm:inline-block" />
              </button>

              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-xl shadow-forge border border-forge-line overflow-hidden py-1 z-50">
                  <div className="px-4 py-2 border-b border-slate-100 mb-1">
                    <p className="text-sm font-medium text-slate-900 truncate">{user.name}</p>
                    <p className="text-xs text-slate-500 truncate">{user.email}</p>
                  </div>
                  <button 
                    onClick={handleSignOut} 
                    className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2 transition-colors"
                  >
                    <LogOut className="w-4 h-4" /> Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Desktop Navigation Rail */}
      <aside className={`fixed left-0 top-0 bottom-0 ${sidebarWidth} flex-col py-6 hidden md:flex z-40 bg-surface/50 border-r border-forge-line backdrop-blur-md transition-all duration-300 ease-forge`}>
        <div className="px-4 mb-8 flex justify-end">
           <button onClick={toggleNav} className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors" title={navExpanded ? "Collapse sidebar" : "Expand sidebar"}>
             {navExpanded ? <PanelLeftClose className="w-5 h-5" /> : <PanelLeftOpen className="w-5 h-5" />}
           </button>
        </div>
        
        <nav className="flex flex-col gap-2 w-full px-3">
          {navItems.filter(item => !item.bottom).map((item) => {
            const isActive = item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href);
            return (
              <Link 
                key={item.href}
                href={item.href} 
                title={!navExpanded ? item.name : undefined}
                className={`flex items-center gap-3 p-3 rounded-xl transition-all duration-200 ease-forge ${
                  isActive ? "bg-blue-50 text-blue-700 shadow-sm font-medium" : "text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                } ${!navExpanded ? "justify-center" : ""}`}
              >
                <div className="relative">
                  <item.icon className="w-5 h-5" />
                  {isActive && !navExpanded && <span className="absolute -left-6 top-1/2 -translate-y-1/2 w-1 h-5 bg-blue-600 rounded-r-full"></span>}
                </div>
                {navExpanded && <span>{item.name}</span>}
                {isActive && navExpanded && <span className="ml-auto w-1.5 h-1.5 bg-blue-600 rounded-full"></span>}
              </Link>
            );
          })}
        </nav>
        
        <nav className="flex flex-col gap-2 w-full px-3 mt-auto">
          {navItems.filter(item => item.bottom).map((item) => {
            const isActive = pathname?.startsWith(item.href);
            return (
              <Link 
                key={item.href}
                href={item.href} 
                title={!navExpanded ? item.name : undefined}
                className={`flex items-center gap-3 p-3 rounded-xl transition-all duration-200 ease-forge ${
                  isActive ? "bg-blue-50 text-blue-700 shadow-sm font-medium" : "text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                } ${!navExpanded ? "justify-center" : ""}`}
              >
                <item.icon className="w-5 h-5" />
                {navExpanded && <span>{item.name}</span>}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white/90 backdrop-blur-md border-t border-forge-line pb-safe">
        <div className="flex items-center justify-around p-2">
          {navItems.map(item => {
            const isActive = item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href);
            return (
              <Link 
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-1 p-2 rounded-lg transition-colors ${isActive ? 'text-blue-600' : 'text-slate-500'}`}
              >
                <item.icon className="w-5 h-5" />
                <span className="text-[10px] font-medium">{item.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
      
      {/* Main Content Area */}
      <main className={`flex-1 mt-[100px] mb-20 md:mb-0 relative z-10 transition-all duration-300 ease-forge ml-0 ${navExpanded ? "md:ml-[220px]" : "md:ml-[72px]"}`}>
        <div className="max-w-[1320px] w-full mx-auto px-4 sm:px-6 md:px-8 lg:px-10 py-4">
          {children}
        </div>
      </main>
    </div>
  );
}
