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
      <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-4">
            <span className="flex items-center gap-2 text-[11px] font-mono font-medium tracking-widest uppercase text-blue-600">
              <span className="w-2 h-2 rounded-full bg-blue-600 shadow-[0_0_0_4px_rgba(37,99,235,0.1)]"></span>
              Workspace
            </span>
          </div>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-slate-900 mb-4 max-w-2xl leading-tight">
            Ready for your next engineering task.
          </h1>
        </div>
        <Button onClick={() => router.push('/repositories')} className="w-full md:w-auto">
          <Plus className="w-4 h-4" /> Import Repository
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-slate-500 mb-1">
              <Database className="w-4 h-4" />
              <span className="font-mono text-xs uppercase tracking-wider font-semibold">Imported Repositories</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-semibold text-slate-900">{loading ? "-" : repos.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-slate-500 mb-1">
              <Activity className="w-4 h-4" />
              <span className="font-mono text-xs uppercase tracking-wider font-semibold">Active Runs</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-semibold text-slate-900">0</div>
          </CardContent>
        </Card>
      </div>

      <h2 className="text-2xl font-semibold tracking-tight text-slate-900 mb-6">Recent Repositories</h2>
      
      {loading ? (
        <div className="flex items-center justify-center py-24 text-slate-500 gap-3">
          <Loader2 className="w-5 h-5 animate-spin" /> 
          <span className="font-medium">Loading repositories...</span>
        </div>
      ) : repos.length === 0 ? (
        <Card className="text-center py-16">
          <CardContent className="flex flex-col items-center">
            <Database className="w-12 h-12 text-slate-300 mb-6" />
            <h3 className="text-xl font-semibold text-slate-900 mb-3">No repositories imported</h3>
            <p className="text-slate-500 mb-8 max-w-md mx-auto">
              Import a repository from GitHub to start planning and executing tasks with Forge.
            </p>
            <Button onClick={() => router.push('/repositories')} variant="secondary">
              <Github className="w-4 h-4" /> Browse GitHub
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {repos.map(repo => (
            <Link href={`/repositories/${repo.id}`} key={repo.id} className="block group">
              <Card className="h-full hover:border-blue-300 hover:shadow-lg transition-all duration-300">
                <CardContent className="p-6 flex flex-col h-full justify-between">
                  <div>
                    <div className="flex items-start justify-between gap-3 mb-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-slate-100 rounded-lg group-hover:bg-blue-50 transition-colors">
                          <Github className="w-5 h-5 text-slate-600 group-hover:text-blue-600" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-slate-900 text-lg truncate" title={repo.name}>{repo.name}</h3>
                          <p className="text-sm text-slate-500 truncate">{repo.owner}/{repo.name}</p>
                        </div>
                      </div>
                      <Badge variant={repo.status === 'READY' ? 'success' : 'warning'}>
                        {repo.status}
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center justify-between border-t border-slate-100 pt-4 mt-6">
                    <div className="text-xs text-slate-500 flex items-center gap-2 font-mono">
                      <Database className="w-3 h-3" /> {repo.default_branch}
                    </div>
                    <span className="text-blue-600 text-sm font-medium flex items-center gap-1 group-hover:gap-2 transition-all">
                      View <ArrowRight className="w-4 h-4" />
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
