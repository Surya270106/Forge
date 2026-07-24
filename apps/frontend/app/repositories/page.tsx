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
      <div className="mb-6">
        <Link href="/" className="inline-flex items-center gap-2 text-slate-500 hover:text-blue-600 transition-colors mb-6 text-sm font-medium">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 mb-2 flex items-center gap-3">
              <Github className="w-8 h-8 text-slate-700" /> Import from GitHub
            </h1>
            <p className="text-slate-500">Select a repository from your GitHub account to import into Forge AI.</p>
          </div>
          <div className="relative w-full md:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search repositories..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-24 text-slate-500 gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" /> 
          <p className="font-medium">Fetching your repositories from GitHub...</p>
        </div>
      ) : githubRepos.length === 0 ? (
        <Card className="text-center py-16">
          <CardContent>
            <p className="text-slate-500">No repositories found in your GitHub account.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredRepos.map(repo => (
            <Card key={repo.name} className="hover:border-blue-200 hover:shadow-md transition-all duration-200">
              <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-semibold text-slate-900 text-lg">{repo.owner}/{repo.name}</h3>
                    {repo.is_private ? (
                      <Badge variant="outline" className="gap-1 bg-slate-50">
                        <Lock className="w-3 h-3" /> Private
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1 bg-slate-50">
                        <Unlock className="w-3 h-3" /> Public
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-500">{repo.description || "No description provided."}</p>
                </div>
                
                <Button
                  onClick={() => handleImport(repo)}
                  disabled={importing === repo.name}
                  variant={importing === repo.name ? "secondary" : "primary"}
                  className="w-full md:w-auto min-w-[120px]"
                >
                  {importing === repo.name ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</>
                  ) : (
                    <><Plus className="w-4 h-4" /> Import</>
                  )}
                </Button>
              </CardContent>
            </Card>
          ))}
          {filteredRepos.length === 0 && (
             <div className="text-center py-12 text-slate-500">
               No repositories match your search.
             </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
