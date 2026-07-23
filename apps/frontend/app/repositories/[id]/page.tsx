'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Database, Search, ArrowLeft, Loader2, GitBranch, Folder, Code2, AlertTriangle, CheckCircle, BrainCircuit } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

export default function RepositoryDetailPage() {
  const params = useParams();
  const repoId = params.id as string;
  const router = useRouter();

  const [repo, setRepo] = useState<any>(null);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [intent, setIntent] = useState("");

  const fetchRepo = async () => {
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/imported`, {
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "" }
      });
      if (res.ok) {
        const data = await res.json();
        const found = data.repositories.find((r: any) => r.id === repoId);
        setRepo(found);
      }
    } catch (e) { console.error(e); }
  };

  const fetchPlans = async () => {
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans`, {
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "" }
      });
      if (res.ok) {
        const data = await res.json();
        setPlans(data.plans.filter((p: any) => p.repository_id === repoId));
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    Promise.all([fetchRepo(), fetchPlans()]).finally(() => setLoading(false));
    
    // Poll for status updates
    const interval = setInterval(() => {
      fetchRepo();
      fetchPlans();
    }, 5000);
    return () => clearInterval(interval);
  }, [repoId]);

  const handleIndex = async () => {
    setActionLoading(true);
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    try {
      await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/memory/repositories/${repoId}/index`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "", "Content-Type": "application/json" },
        body: JSON.stringify({ branch: repo.default_branch || "main" })
      });
      alert("Indexing started in the background!");
    } catch (e) {
      console.error(e);
      alert("Failed to start indexing");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreatePlan = async () => {
    if (!intent.trim()) return;
    setActionLoading(true);
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/${repoId}/plans`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "", "Content-Type": "application/json" },
        body: JSON.stringify({ intent })
      });
      if (res.ok) {
        const newPlan = await res.json();
        router.push(`/tasks/${newPlan.id}`);
      }
    } catch (e) {
      console.error(e);
      alert("Failed to create plan");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <div className="p-20 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-muted" /></div>;
  }

  if (!repo) {
    return <div className="p-20 text-center text-white">Repository not found.</div>;
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <Link href="/" className="inline-flex items-center gap-2 text-muted hover:text-white transition-colors mb-6 text-sm font-medium">
        <ArrowLeft className="w-4 h-4" /> Back to Dashboard
      </Link>
      
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold tracking-tight text-white">{repo.name}</h1>
            <span className={`text-xs font-semibold px-2 py-1 rounded-full flex items-center gap-1 ${
              repo.status === 'READY' ? 'bg-green-900/30 text-green-400 border border-green-800' :
              repo.status === 'FAILED' ? 'bg-red-900/30 text-red-400 border border-red-800' :
              'bg-yellow-900/30 text-yellow-400 border border-yellow-800'
            }`}>
              {repo.status === 'READY' && <CheckCircle className="w-3 h-3" />}
              {repo.status === 'FAILED' && <AlertTriangle className="w-3 h-3" />}
              {repo.status}
            </span>
          </div>
          <p className="text-muted flex items-center gap-2">
            <GitBranch className="w-4 h-4" /> {repo.owner}/{repo.name} &bull; Default branch: {repo.default_branch}
          </p>
        </div>
        
        <div className="flex gap-3">
          <button
            onClick={handleIndex}
            disabled={actionLoading || repo.status !== 'READY'}
            className="bg-surface border border-border hover:bg-surface/80 text-white px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Database className="w-4 h-4" /> Index Codebase
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted flex items-center gap-2 mb-2"><Folder className="w-4 h-4" /> Status</div>
          <div className="text-lg font-medium text-white">{repo.status}</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted flex items-center gap-2 mb-2"><Code2 className="w-4 h-4" /> Source</div>
          <div className="text-lg font-medium text-white truncate" title={repo.clone_url}>{repo.clone_url}</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="text-muted flex items-center gap-2 mb-2"><Search className="w-4 h-4" /> Memory Index</div>
          <div className="text-lg font-medium text-yellow-400">Needs Indexing</div>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 mb-10">
        <h2 className="text-xl font-semibold tracking-tight text-white mb-4 flex items-center gap-2">
          <BrainCircuit className="w-5 h-5 text-accent" /> Autonomous Tasks
        </h2>
        
        <div className="mb-6 flex gap-3">
          <input 
            type="text" 
            value={intent}
            onChange={e => setIntent(e.target.value)}
            placeholder="What should the AI build or fix? (e.g. 'Add a dark mode toggle', 'Fix the memory leak in parser')"
            className="flex-1 bg-black border border-border rounded-lg px-4 py-2 text-white outline-none focus:border-accent transition-colors"
          />
          <button
            onClick={handleCreatePlan}
            disabled={actionLoading || !intent.trim() || repo.status !== 'READY'}
            className="bg-accent hover:bg-accent/90 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create Plan"}
          </button>
        </div>

        {plans.length > 0 && (
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-black/50 border-b border-border text-muted text-sm">
                  <th className="p-3 font-medium">Intent</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Created</th>
                  <th className="p-3 font-medium w-24"></th>
                </tr>
              </thead>
              <tbody>
                {plans.map(plan => (
                  <tr key={plan.id} className="border-b border-border/50 hover:bg-black/20 transition-colors">
                    <td className="p-3 text-white truncate max-w-[300px]">{plan.intent}</td>
                    <td className="p-3">
                      <span className={`text-xs px-2 py-1 rounded bg-gray-900 text-gray-300 border border-gray-700`}>
                        {plan.status}
                      </span>
                    </td>
                    <td className="p-3 text-muted text-sm">{new Date(plan.created_at).toLocaleDateString()}</td>
                    <td className="p-3 text-right">
                      <Link href={`/tasks/${plan.id}`} className="text-accent hover:text-white transition-colors text-sm font-medium">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
