'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../config/env";
import { Github, Loader2, Plus, ArrowLeft, Lock, Unlock, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "../components/AppShell";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";

export default function RepositoriesPage() {
  const [githubRepos, setGithubRepos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const router = useRouter();

  useEffect(() => {
    const fetchGithubRepos = async () => {
      const token = localStorage.getItem("forge_token");
      
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/github-repos`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          setGithubRepos(data.repositories);
        } else if (res.status === 401 || res.status === 400) {
          router.push('/login');
        }
      } catch (err) {
        console.error("Failed to fetch GitHub repos", err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchGithubRepos();
  }, [router]);

  const handleImport = async (repo: any) => {
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    
    if (!orgId) {
      alert("No organization selected. Please wait or re-login.");
      return;
    }

    setImporting(repo.name);
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/import`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Organization-Id": orgId,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          clone_url: repo.clone_url,
          owner: repo.owner,
          name: repo.name,
          branch: repo.default_branch || "main",
          is_private: repo.is_private
        })
      });
      
      if (res.ok) {
        router.push('/');
      } else {
        const err = await res.json();
        alert(`Failed to import: ${err.detail}`);
        setImporting(null);
      }
    } catch (err) {
      console.error(err);
      alert("An error occurred during import.");
      setImporting(null);
    }
  };

  const filteredRepos = githubRepos.filter(repo => 
    repo.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    repo.owner.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <AppShell>
      <div className="mb-8">
        <Link href="/" className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 transition-colors mb-6 text-sm font-medium">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <h1 className="text-[clamp(32px,3vw,44px)] font-semibold tracking-tight text-slate-900 mb-2 flex items-center gap-3">
              <div className="w-10 h-10 bg-slate-900 text-white rounded-xl flex items-center justify-center shadow-sm">
                <Github className="w-5 h-5" />
              </div>
              Import Repository
            </h1>
            <p className="text-slate-500 max-w-xl">Select a repository from your GitHub account to connect to Forge AI.</p>
          </div>
          <div className="relative w-full md:w-[320px] shrink-0">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search repositories..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 h-[42px] bg-white border border-forge-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
            />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-32 text-slate-500 gap-4">
          <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
          <p className="font-medium text-sm">Fetching your repositories from GitHub...</p>
        </div>
      ) : githubRepos.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-forge-line rounded-2xl bg-white/50">
          <Github className="w-12 h-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500 font-medium">No repositories found in your GitHub account.</p>
        </div>
      ) : (
        <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-forge-line shadow-sm overflow-hidden">
          <div className="divide-y divide-slate-100/80">
            {filteredRepos.map(repo => (
              <div key={repo.name} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/50 transition-colors">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3 mb-1.5">
                    <h3 className="font-semibold text-slate-900 text-[15px] truncate">{repo.owner}/{repo.name}</h3>
                    {repo.is_private ? (
                      <Badge variant="outline" className="text-[10px] px-2 py-0 h-5 bg-slate-50 text-slate-500 border-slate-200">
                        <Lock className="w-2.5 h-2.5 mr-1 inline" /> Private
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] px-2 py-0 h-5 bg-slate-50 text-slate-500 border-slate-200">
                        <Unlock className="w-2.5 h-2.5 mr-1 inline" /> Public
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-500 truncate pr-4">{repo.description || "No description provided."}</p>
                </div>
                
                <div className="shrink-0">
                  <Button
                    onClick={() => handleImport(repo)}
                    disabled={importing === repo.name}
                    variant={importing === repo.name ? "secondary" : "primary"}
                    className="w-full sm:w-[120px]"
                  >
                    {importing === repo.name ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /> Importing</>
                    ) : (
                      <><Plus className="w-4 h-4" /> Import</>
                    )}
                  </Button>
                </div>
              </div>
            ))}
            {filteredRepos.length === 0 && (
               <div className="text-center py-16 text-slate-500 text-sm font-medium">
                 No repositories match your search.
               </div>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
