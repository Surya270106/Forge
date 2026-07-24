'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { CheckCircle, Play, Loader2, GitMerge, FileCode, Check, X, RefreshCcw, Activity, ArrowLeft } from "lucide-react";
import { AppShell } from "../../components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import Link from "next/link";

export default function TaskPage({ params }: { params: { id: string } }) {
  const [plan, setPlan] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const [mutations, setMutations] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'plan' | 'execution'>('plan');

  const fetchExecution = async (execId: string) => {
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${execId}`, {
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "" }
      });
      if (res.ok) {
        const data = await res.json();
        setExecutionStatus(data.status);
        if (data.status === "COMPLETED" || data.status === "FAILED") {
          setExecuting(false);
          const mutRes = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${execId}/mutations`, {
            headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "" }
          });
          if (mutRes.ok) {
            const mutData = await mutRes.json();
            setMutations(mutData.mutations);
          }
        }
      }
      const logsRes = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${execId}/logs`, {
        headers: { "Authorization": `Bearer ${token}`, "X-Organization-Id": orgId || "" }
      });
      if (logsRes.ok) {
        const logsData = await logsRes.json();
        setLogs(logsData.map((l: any) => l.message));
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (executionId && executing) {
      const interval = setInterval(() => {
        fetchExecution(executionId);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [executionId, executing]);

  const fetchPlan = async () => {
    const token = localStorage.getItem("forge_token");
    const orgId = localStorage.getItem("forge_org_id");
    
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans/${params.id}`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Organization-Id": orgId || ""
        }
      });
      if (res.ok) {
        const data = await res.json();
        setPlan(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlan();
  }, [params.id]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans/${params.id}/approve`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Organization-Id": orgId || ""
        }
      });
      await fetchPlan();
    } catch (err) {
      console.error(err);
    } finally {
      setApproving(false);
    }
  };

  const handleExecute = async () => {
    setExecuting(true);
    setActiveTab('execution');
    setLogs(["Starting execution engine..."]);
    try {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/plans/${params.id}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Organization-Id": orgId || "",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({})
      });
      if (res.ok) {
        const data = await res.json();
        setExecutionId(data.id);
        setExecutionStatus("PENDING");
      }
    } catch (err) {
      console.error(err);
      setExecuting(false);
      setExecutionStatus("FAILED");
    }
  };

  if (loading) return (
    <AppShell>
      <div className="flex flex-col items-center justify-center py-24 text-slate-500 gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
        <span className="font-medium">Loading plan...</span>
      </div>
    </AppShell>
  );

  if (!plan) return (
    <AppShell>
      <div className="p-8 text-red-500 font-medium">Plan not found.</div>
    </AppShell>
  );

  return (
    <AppShell>
      <div className="mb-6">
        <Link href={`/repositories/${plan.repository_id}`} className="inline-flex items-center gap-2 text-slate-500 hover:text-blue-600 transition-colors mb-6 text-sm font-medium">
          <ArrowLeft className="w-4 h-4" /> Back to Repository
        </Link>

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Execution Plan</h1>
              <Badge variant={plan.status === 'APPROVED' ? 'success' : 'warning'}>
                {plan.status.replace('_', ' ')}
              </Badge>
            </div>
            <p className="text-slate-600 text-lg">{plan.intent}</p>
          </div>
        </div>

        <div className="flex border-b border-slate-200 mb-8">
          <button 
            onClick={() => setActiveTab('plan')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 ${activeTab === 'plan' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Plan Details
          </button>
          <button 
            onClick={() => setActiveTab('execution')}
            className={`px-4 py-3 font-medium text-sm transition-colors border-b-2 ${activeTab === 'execution' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            Execution Logs
          </button>
        </div>
      </div>

      {activeTab === 'plan' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <Card>
            <CardHeader>
              <CardTitle>Task Graph</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {plan.nodes?.length > 0 ? plan.nodes.map((node: any, idx: number) => (
                  <div key={node.id} className="relative pl-12 border-l-2 border-slate-100 ml-4">
                    <div className="absolute -left-[17px] top-0 w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center text-sm font-bold border border-blue-100">
                      {idx + 1}
                    </div>
                    <div className="mb-2">
                      <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-1 rounded-md uppercase font-semibold tracking-wider">
                        {node.action_type}
                      </span>
                    </div>
                    <h3 className="font-semibold text-slate-900 mb-2">
                      {node.action_type === "edit_file" 
                        ? `Edit file: ${node.target}` 
                        : node.action_type === "command"
                        ? `Run command in ${node.target}`
                        : `${node.action_type} on ${node.target}`}
                    </h3>
                    <div className="text-sm font-mono text-slate-600 bg-slate-50 p-4 rounded-xl border border-slate-100 overflow-x-auto whitespace-pre-wrap">
                      {node.parameters?.changes || node.parameters?.command || JSON.stringify(node.parameters, null, 2)}
                    </div>
                  </div>
                )) : (
                  <div className="text-sm font-mono text-slate-500 p-4 bg-slate-50 rounded-xl border border-slate-100">
                    {JSON.stringify(plan, null, 2)}
                  </div>
                )}
              </div>

              {plan.status === "PENDING_APPROVAL" && (
                <div className="mt-10 border-t border-slate-100 pt-6 flex justify-end gap-4">
                  <Button variant="ghost">Reject</Button>
                  <Button 
                    onClick={handleApprove}
                    disabled={approving}
                  >
                    {approving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <CheckCircle className="w-4 h-4 mr-2" />}
                    Approve Plan
                  </Button>
                </div>
              )}
              
              {plan.status === "APPROVED" && executionStatus === null && (
                <div className="mt-10 border-t border-slate-100 pt-6 flex justify-end">
                  <Button 
                    onClick={handleExecute}
                    disabled={executing}
                    className="bg-green-600 hover:bg-green-700 shadow-green-600/20"
                  >
                    <Play className="w-4 h-4 mr-2" /> Start Execution
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'execution' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <Card className="overflow-hidden flex flex-col h-[600px]">
            <div className="p-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                <FileCode className="w-4 h-4 text-blue-500" /> Terminal Output
              </h2>
              {executionStatus && (
                <Badge variant={executionStatus === 'COMPLETED' ? 'success' : 'default'}>
                  {executionStatus}
                </Badge>
              )}
            </div>
            
            <div className="p-6 flex-1 bg-slate-900 overflow-y-auto font-mono text-sm leading-relaxed">
              {logs.length === 0 ? (
                <div className="text-slate-500 h-full flex items-center justify-center italic">
                  Awaiting execution...
                </div>
              ) : (
                <div className="space-y-1.5">
                  {logs.map((log, i) => (
                    <div key={i} className="flex gap-4 text-slate-300">
                      <span className="text-slate-600 select-none shrink-0 w-6 text-right">{String(i+1).padStart(2, '0')}</span>
                      <span className={log.includes("passed") || log.includes("completed") || log.includes("Successfully") ? "text-green-400" : ""}>{log}</span>
                    </div>
                  ))}
                  {executing && (
                    <div className="flex gap-4 text-blue-400 animate-pulse mt-2">
                      <span className="text-slate-600 select-none shrink-0 w-6 text-right">--</span>
                      <span>Processing...</span>
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {executionStatus === "COMPLETED" && (
              <div className="p-6 border-t border-slate-100 bg-white shrink-0 flex flex-col gap-6">
                <div className="flex items-center gap-3 text-green-600 font-medium">
                  <div className="w-8 h-8 rounded-full bg-green-50 flex items-center justify-center">
                    <CheckCircle className="w-5 h-5" />
                  </div>
                  All mutations applied successfully.
                </div>
                
                {mutations.length > 0 && (
                  <div className="space-y-4">
                    <h3 className="text-xs font-semibold uppercase text-slate-500 tracking-wider">File Changes</h3>
                    {mutations.map(m => (
                      <div key={m.id} className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div className="bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 flex justify-between border-b border-slate-200">
                          <span className="font-mono">{m.file_path}</span>
                          <Badge variant="outline" className="text-xs bg-white">{m.mutation_type}</Badge>
                        </div>
                        <div className="bg-slate-900 p-4 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre">
                          {m.diff_hunk}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                <div className="flex justify-end pt-4">
                  <Button variant="secondary" className="gap-2">
                    <GitMerge className="w-4 h-4" /> Create Pull Request
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}
