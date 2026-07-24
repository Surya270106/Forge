'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Database, ArrowLeft, Loader2, GitBranch, Folder, Code2, AlertTriangle, CheckCircle, BrainCircuit, Search, Play, FileText, History } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "../../components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";

export default function RepositoryDetailPage() {
  const params = useParams();
  const repoId = params.id as string;
  const router = useRouter();

  const [repo, setRepo] = useState<any>(null);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [intent, setIntent] = useState("");
  const [activeTab, setActiveTab] = useState<'overview' | 'memory' | 'plans' | 'runs'>('overview');

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
      setActiveTab('memory');
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
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Failed to create plan: ${err.detail || err.message || res.status}`);
      }
    } catch (e) {
      console.error(e);
      alert("Failed to create plan");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center py-32 text-slate-500 gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
          <span className="font-medium">Loading repository...</span>
        </div>
      </AppShell>
    );
  }

  if (!repo) {
    return (
      <AppShell>
        <div className="py-32 text-center text-slate-500 font-medium">Repository not found.</div>
      </AppShell>
    );
  }

  const activePlans = plans.filter(p => p.status === 'PENDING_APPROVAL');

  return (
    <AppShell>
      <div className="mb-6">
        <Link href="/repositories" className="inline-flex items-center gap-2 text-slate-500 hover:text-blue-600 transition-colors mb-6 text-sm font-medium">
          <ArrowLeft className="w-4 h-4" /> Back to Repositories
        </Link>
        
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900">{repo.name}</h1>
              <Badge variant={repo.status === 'READY' ? 'success' : repo.status === 'FAILED' ? 'destructive' : 'warning'} className="gap-1">
                {repo.status === 'READY' && <CheckCircle className="w-3 h-3" />}
                {repo.status === 'FAILED' && <AlertTriangle className="w-3 h-3" />}
                {repo.status === 'PENDING' && <Loader2 className="w-3 h-3 animate-spin" />}
                {repo.status}
              </Badge>
            </div>
            <p className="text-slate-500 flex items-center gap-2 font-medium">
              <GitBranch className="w-4 h-4" /> {repo.owner}/{repo.name} 
              <span className="text-slate-300 mx-1">&bull;</span> 
              Default branch: <span className="text-slate-700">{repo.default_branch}</span>
            </p>
          </div>
          
          <div className="flex gap-3">
            <Button
              onClick={handleIndex}
              disabled={actionLoading || repo.status !== 'READY'}
              variant="secondary"
              className="hidden md:flex gap-2"
            >
              <Database className="w-4 h-4" /> Index Codebase
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200 mb-8 overflow-x-auto hide-scrollbar">
          <button 
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 whitespace-nowrap ${activeTab === 'overview' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Overview
          </button>
          <button 
            onClick={() => setActiveTab('memory')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 whitespace-nowrap ${activeTab === 'memory' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Memory Index
          </button>
          <button 
            onClick={() => setActiveTab('plans')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 whitespace-nowrap ${activeTab === 'plans' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Proposed Plans <span className="ml-1.5 bg-slate-100 text-slate-600 py-0.5 px-2 rounded-full text-xs">{plans.length}</span>
          </button>
          <button 
            onClick={() => setActiveTab('runs')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 whitespace-nowrap ${activeTab === 'runs' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Runs
          </button>
        </div>
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-8 animate-in fade-in duration-300">
          <Card className="overflow-hidden border-blue-100 shadow-sm shadow-blue-900/5">
            <CardHeader className="bg-blue-50/50 border-blue-100">
              <CardTitle className="flex items-center gap-2 text-blue-900">
                <BrainCircuit className="w-5 h-5 text-blue-600" /> New Engineering Task
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <input 
                  type="text" 
                  value={intent}
                  onChange={e => setIntent(e.target.value)}
                  placeholder="What should Forge build or fix? (e.g. 'Add a dark mode toggle', 'Fix the memory leak')"
                  className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-slate-900 placeholder:text-slate-400 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all text-sm font-medium shadow-sm"
                />
                <Button
                  onClick={handleCreatePlan}
                  disabled={actionLoading || !intent.trim() || repo.status !== 'READY'}
                  className="md:w-32"
                >
                  {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Plan Task"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2 text-slate-500 mb-1">
                  <FileText className="w-4 h-4" />
                  <span className="font-mono text-xs uppercase tracking-wider font-semibold">Active Plans</span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-4xl font-semibold text-slate-900">{activePlans.length}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2 text-slate-500 mb-1">
                  <Play className="w-4 h-4" />
                  <span className="font-mono text-xs uppercase tracking-wider font-semibold">Active Runs</span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-4xl font-semibold text-slate-900">0</div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {activeTab === 'memory' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <Card>
            <CardHeader>
              <CardTitle>Memory Index Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4 p-6 bg-slate-50 rounded-xl border border-slate-100">
                {repo.indexing_status === 'COMPLETED' ? (
                  <div className="flex flex-col gap-1">
                    <span className="text-green-600 flex items-center gap-2 font-medium text-lg"><CheckCircle className="w-5 h-5"/> Fully Indexed</span>
                    <p className="text-sm text-slate-500">The repository memory is up to date.</p>
                  </div>
                ) : repo.indexing_status === 'PARSING' || repo.indexing_status === 'SCANNING' || repo.indexing_status === 'PENDING' ? (
                  <div className="flex flex-col gap-1">
                    <span className="text-blue-600 flex items-center gap-2 font-medium text-lg"><Loader2 className="w-5 h-5 animate-spin"/> Indexing in Progress</span>
                    <p className="text-sm text-slate-500">Forge is analyzing the repository AST and dependencies.</p>
                  </div>
                ) : repo.indexing_status === 'FAILED' ? (
                  <div className="flex flex-col gap-1">
                    <span className="text-red-600 flex items-center gap-2 font-medium text-lg"><AlertTriangle className="w-5 h-5"/> Indexing Failed</span>
                    <p className="text-sm text-slate-500">An error occurred while building the memory index.</p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    <span className="text-slate-700 font-medium text-lg">Needs Indexing</span>
                    <p className="text-sm text-slate-500">Forge has not built a memory index for this repository yet.</p>
                  </div>
                )}
                
                <div className="ml-auto">
                  <Button onClick={handleIndex} disabled={actionLoading || repo.status !== 'READY'} variant="secondary">
                    <Database className="w-4 h-4 mr-2" /> Re-index
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'plans' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <Card>
            <CardHeader>
              <CardTitle>Proposed Plans</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-y border-slate-200 text-slate-500 text-xs uppercase tracking-wider font-mono">
                    <th className="p-4 font-semibold">Intent</th>
                    <th className="p-4 font-semibold">Status</th>
                    <th className="p-4 font-semibold">Created</th>
                    <th className="p-4 font-semibold w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {plans.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-slate-500">No plans created yet.</td>
                    </tr>
                  ) : (
                    plans.map(plan => (
                      <tr key={plan.id} className="border-b border-slate-100 hover:bg-slate-50/50 transition-colors group">
                        <td className="p-4 text-slate-900 font-medium truncate max-w-[400px]">{plan.intent}</td>
                        <td className="p-4">
                          <Badge variant={plan.status === 'PENDING_APPROVAL' ? 'warning' : plan.status === 'APPROVED' ? 'success' : 'default'}>
                            {plan.status.replace('_', ' ')}
                          </Badge>
                        </td>
                        <td className="p-4 text-slate-500 text-sm">{new Date(plan.created_at).toLocaleDateString()}</td>
                        <td className="p-4 text-right">
                          <Link href={`/tasks/${plan.id}`} className="text-blue-600 hover:text-blue-800 transition-colors text-sm font-medium flex items-center justify-end gap-1">
                            Review <ArrowLeft className="w-3 h-3 rotate-180" />
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'runs' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <Card className="py-16 text-center">
            <CardContent>
              <History className="w-12 h-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-500">Execution history will appear here once plans are approved.</p>
            </CardContent>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
