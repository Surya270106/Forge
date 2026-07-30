'use client';

import React, { useEffect, useState } from "react";
import { env } from "../config/env";
import { Github, Database, ArrowRight, Loader2, Plus, Activity } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "./components/AppShell";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Badge } from "./components/ui/badge";

export default function DashboardPage() {
  const [repos, setRepos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const fetchRepos = async () => {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/imported`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Organization-Id": orgId || ""
          },
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        if (res.ok) {
          const data = await res.json();
          setRepos(data.repositories);
        }
      } catch (err) {
        clearTimeout(timeoutId);
        console.error("Failed to fetch repos:", err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchRepos();
  }, []);

  return (
    <AppShell>
      {/* Refined Header */}
      <div className="mb-8 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="flex items-center gap-2 text-[10px] font-mono font-bold tracking-[0.2em] uppercase text-blue-600">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 shadow-[0_0_0_3px_rgba(37,99,235,0.1)]"></span>
              Workspace
            </span>
          </div>
          <h1 className="text-[clamp(32px,3vw,44px)] font-semibold tracking-tight text-slate-900 leading-[1.1]">
            Ready for your next engineering task.
          </h1>
        </div>
        <div className="shrink-0">
          <Button onClick={() => router.push('/repositories')} variant="primary" size="lg" className="w-full lg:w-auto shadow-forge">
            <Plus className="w-4 h-4" /> Import Repository
          </Button>
        </div>
      </div>

      {/* Compact Evidence Panels */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-10">
        <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-forge-line p-5 shadow-sm flex items-center justify-between hover:bg-white/95 transition-colors">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-50 text-blue-600 rounded-xl">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-mono font-medium tracking-wider text-slate-500 uppercase">Imported Repositories</p>
              <div className="text-3xl font-semibold text-slate-900 mt-1 leading-none">{loading ? "-" : repos.length}</div>
            </div>
          </div>
        </div>
        <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-forge-line p-5 shadow-sm flex items-center justify-between hover:bg-white/95 transition-colors">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-mono font-medium tracking-wider text-slate-500 uppercase">Active Runs</p>
              <div className="text-3xl font-semibold text-slate-900 mt-1 leading-none">0</div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Repositories Grid */}
      <h2 className="text-xl md:text-2xl font-semibold tracking-tight text-slate-900 mb-5">Recent Repositories</h2>
      
      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-500 gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-blue-500" /> 
          <span className="font-medium text-sm">Loading repositories...</span>
        </div>
      ) : repos.length === 0 ? (
        <Card className="text-center py-16 border-dashed border-2 border-slate-200/60 bg-transparent shadow-none hover:bg-white/30 transition-colors">
          <CardContent className="flex flex-col items-center">
            <div className="w-16 h-16 bg-white rounded-2xl shadow-sm border border-forge-line flex items-center justify-center mb-6">
              <Database className="w-8 h-8 text-blue-600/70" />
            </div>
            <h3 className="text-xl font-semibold text-slate-900 mb-2">No repositories imported</h3>
            <p className="text-slate-500 mb-8 max-w-sm mx-auto text-sm leading-relaxed">
              Import a repository from GitHub to start planning and executing tasks with Forge.
            </p>
            <Button onClick={() => router.push('/repositories')} variant="secondary">
              <Github className="w-4 h-4" /> Browse GitHub
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5">
          {repos.map(repo => (
            <Link href={`/repositories/${repo.id}`} key={repo.id} className="block group">
              <Card className="h-full border-forge-line hover:border-blue-300 hover:shadow-forge hover:-translate-y-0.5 transition-all duration-300 ease-forge flex flex-col justify-between">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-slate-50 border border-slate-100 rounded-lg group-hover:bg-blue-50 group-hover:border-blue-100 transition-colors shrink-0">
                        <Github className="w-4 h-4 text-slate-600 group-hover:text-blue-600" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-slate-900 text-[15px] truncate" title={repo.name}>{repo.name}</h3>
                        <p className="text-xs text-slate-500 truncate" title={`${repo.owner}/${repo.name}`}>{repo.owner}</p>
                      </div>
                    </div>
                    <Badge variant={repo.status === 'READY' ? 'success' : 'warning'} className="shrink-0 text-[10px] px-2 py-0.5">
                      {repo.status}
                    </Badge>
                  </div>
                  
                  <div className="flex items-center justify-between border-t border-slate-100/60 pt-4 mt-2">
                    <div className="text-[11px] text-slate-400 flex items-center gap-1.5 font-mono">
                      <Database className="w-3 h-3" /> {repo.default_branch}
                    </div>
                    <span className="text-blue-600 text-xs font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all duration-300 ease-forge">
                      View <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
