'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../config/env";
import { Github, Loader2, Plus, ArrowLeft, Lock, Unlock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function RepositoriesPage() {
  const [githubRepos, setGithubRepos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<string | null>(null);
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
          // Token invalid or missing, redirect to login
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
        // Navigate back to dashboard where it should appear
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

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <Link href="/" className="inline-flex items-center gap-2 text-muted hover:text-white transition-colors mb-6 text-sm font-medium">
        <ArrowLeft className="w-4 h-4" /> Back to Dashboard
      </Link>
      
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
          <Github className="w-8 h-8" /> Import from GitHub
        </h1>
        <p className="text-muted">Select a repository from your GitHub account to import into Forge AI.</p>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-accent" /> 
          <p>Fetching your repositories from GitHub...</p>
        </div>
      ) : githubRepos.length === 0 ? (
        <div className="bg-surface border border-border border-dashed rounded-xl p-12 text-center">
          <p className="text-muted">No repositories found in your GitHub account.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {githubRepos.map(repo => (
            <div key={repo.name} className="bg-surface border border-border rounded-xl p-5 flex items-center justify-between hover:border-accent/30 transition-colors">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="font-medium text-white text-lg">{repo.owner}/{repo.name}</h3>
                  {repo.is_private ? (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider bg-gray-800 text-gray-400 flex items-center gap-1">
                      <Lock className="w-3 h-3" /> Private
                    </span>
                  ) : (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider bg-gray-800 text-gray-400 flex items-center gap-1">
                      <Unlock className="w-3 h-3" /> Public
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted">{repo.description || "No description provided."}</p>
              </div>
              
              <button
                onClick={() => handleImport(repo)}
                disabled={importing === repo.name}
                className="bg-white text-black hover:bg-gray-200 disabled:opacity-50 px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {importing === repo.name ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Importing...</>
                ) : (
                  <><Plus className="w-4 h-4" /> Import</>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
