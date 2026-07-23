'use client';

import React, { useEffect, useState } from "react";
import { env } from "../config/env";
import { Github, Database, Search, ArrowRight, Loader2, Plus, Server, Activity } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const [repos, setRepos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const fetchRepos = async () => {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/imported`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Organization-Id": orgId || ""
          }
        });
        if (res.ok) {
          const data = await res.json();
          setRepos(data.repositories);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchRepos();
  }, []);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Dashboard</h1>
          <p className="text-muted">Welcome to Forge AI. Manage your imported repositories and runs.</p>
        </div>
        <button
          onClick={() => router.push('/repositories')} 
          className="bg-accent hover:bg-accent/90 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> Import Repository
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between">
          <div className="text-muted flex items-center gap-2 mb-2"><Database className="w-4 h-4" /> Imported Repos</div>
          <div className="text-3xl font-bold text-white">{loading ? "-" : repos.length}</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between">
          <div className="text-muted flex items-center gap-2 mb-2"><Activity className="w-4 h-4" /> Active Runs</div>
          <div className="text-3xl font-bold text-white">0</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6 flex flex-col justify-between">
          <div className="text-muted flex items-center gap-2 mb-2"><Server className="w-4 h-4" /> Execution Nodes</div>
          <div className="text-3xl font-bold text-green-400">Online</div>
        </div>
      </div>

      <h2 className="text-xl font-semibold tracking-tight text-white mb-4">Your Repositories</h2>
      
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted gap-3">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading repositories...
        </div>
      ) : repos.length === 0 ? (
        <div className="bg-surface border border-border border-dashed rounded-xl p-12 text-center">
          <Database className="w-12 h-12 text-muted mx-auto mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">No repositories imported</h3>
          <p className="text-muted mb-6">Import a repository from GitHub to start using Forge AI.</p>
          <button
            onClick={() => router.push('/repositories')} 
            className="bg-accent hover:bg-accent/90 text-white px-6 py-2 rounded-lg font-medium transition-colors inline-flex items-center gap-2"
          >
            <Github className="w-4 h-4" /> Browse GitHub
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {repos.map(repo => (
            <Link href={`/repositories/${repo.id}`} key={repo.id} className="bg-surface border border-border rounded-xl p-5 hover:border-accent/50 transition-colors flex flex-col justify-between group">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <Github className="w-5 h-5 text-muted" />
                  <h3 className="font-medium text-white truncate" title={repo.name}>{repo.name}</h3>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider ${repo.status === 'READY' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'}`}>
                    {repo.status}
                  </span>
                </div>
                <p className="text-sm text-muted mb-4 h-5">{repo.owner}/{repo.name}</p>
              </div>
              <div className="flex items-center justify-between border-t border-border pt-4">
                <div className="text-xs text-muted flex items-center gap-1">
                  <Database className="w-3 h-3" /> {repo.default_branch}
                </div>
                <span className="text-accent group-hover:text-white text-sm font-medium flex items-center gap-1 transition-colors">
                  View <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
