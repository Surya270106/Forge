'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { CheckCircle, Play, Loader2, GitMerge, FileCode, Check, X, RefreshCcw, Activity } from "lucide-react";

export default function TaskPage({ params }: { params: { id: string } }) {
  const [plan, setPlan] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const [mutations, setMutations] = useState<any[]>([]);

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

  if (loading) return <div className="p-8 animate-pulse text-muted">Loading plan...</div>;
  if (!plan) return <div className="p-8 text-red-400">Plan not found.</div>;

  return (
    <div className="p-8 max-w-6xl mx-auto flex flex-col gap-8 h-full overflow-hidden">
      <div className="flex items-start justify-between shrink-0">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-8 h-8 text-accent" />
            <h1 className="text-3xl font-bold tracking-tight text-white">Execution Plan</h1>
          </div>
          <p className="text-muted">Intent: {plan.intent}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${plan.status === 'APPROVED' ? 'bg-blue-900/30 text-blue-400 border border-blue-900/50' : 'bg-yellow-900/30 text-yellow-400 border border-yellow-900/50'}`}>
          {plan.status}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-1 overflow-hidden min-h-0">
        
        {/* Left Column: Plan Details */}
        <div className="flex flex-col gap-6 overflow-y-auto pr-2">
          <div className="bg-surface border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center justify-between">
              Task Graph
            </h2>
            <div className="space-y-4">
              {plan.nodes?.length > 0 ? plan.nodes.map((node: any, idx: number) => (
                <div key={node.id} className="border border-border rounded-lg p-4 bg-black relative pl-12">
                  <div className="absolute left-4 top-4 w-5 h-5 rounded-full bg-accent text-white flex items-center justify-center text-xs font-bold">
                    {idx + 1}
                  </div>
                  <h3 className="font-medium text-white mb-1">{node.description}</h3>
                  <div className="flex gap-2">
                    <span className="text-[10px] bg-gray-800 text-gray-300 px-2 py-0.5 rounded uppercase">{node.status}</span>
                    <span className="text-[10px] bg-gray-800 text-gray-300 px-2 py-0.5 rounded uppercase">{node.type}</span>
                  </div>
                </div>
              )) : (
                <div className="text-sm font-mono text-gray-400 p-4 bg-black rounded-lg">
                  {JSON.stringify(plan, null, 2)}
                </div>
              )}
            </div>

            {plan.status === "PENDING_APPROVAL" && (
              <div className="mt-8 border-t border-border pt-6 flex justify-end gap-3">
                <button className="px-4 py-2 text-muted hover:text-white transition-colors">
                  Reject
                </button>
                <button 
                  onClick={handleApprove}
                  disabled={approving}
                  className="bg-accent hover:bg-accent/90 text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  {approving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                  Approve Plan
                </button>
              </div>
            )}
            
            {plan.status === "APPROVED" && executionStatus === null && (
              <div className="mt-8 border-t border-border pt-6 flex justify-end">
                <button 
                  onClick={handleExecute}
                  disabled={executing}
                  className="bg-green-600 hover:bg-green-500 text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  <Play className="w-4 h-4" /> Start Execution
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Execution */}
        <div className="flex flex-col gap-6 overflow-hidden">
          <div className="bg-surface border border-border rounded-xl flex flex-col h-full overflow-hidden">
            <div className="p-4 border-b border-border bg-black/50 shrink-0 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <FileCode className="w-4 h-4 text-accent" /> Execution Logs
              </h2>
              {executionStatus && (
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase ${executionStatus === 'COMPLETED' ? 'bg-green-900/30 text-green-400' : 'bg-blue-900/30 text-blue-400'}`}>
                  {executionStatus}
                </span>
              )}
            </div>
            
            <div className="p-4 flex-1 bg-black overflow-y-auto font-mono text-sm leading-relaxed">
              {logs.length === 0 ? (
                <div className="text-gray-600 h-full flex items-center justify-center italic">
                  Awaiting execution...
                </div>
              ) : (
                <div className="space-y-1">
                  {logs.map((log, i) => (
                    <div key={i} className="flex gap-3 text-gray-300">
                      <span className="text-gray-600 select-none shrink-0">{String(i+1).padStart(2, '0')}</span>
                      <span className={log.includes("passed") || log.includes("completed") ? "text-green-400" : ""}>{log}</span>
                    </div>
                  ))}
                  {executing && (
                    <div className="flex gap-3 text-accent animate-pulse mt-2">
                      <span className="text-gray-600 select-none shrink-0">--</span>
                      <span>Processing...</span>
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {executionStatus === "COMPLETED" && (
              <div className="p-4 border-t border-border bg-black/50 shrink-0 flex flex-col gap-4">
                <span className="text-sm font-medium text-white flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400" /> All mutations applied successfully.
                </span>
                
                {mutations.length > 0 && (
                  <div className="space-y-3 mt-2">
                    <h3 className="text-xs font-semibold uppercase text-muted tracking-wider">File Changes</h3>
                    {mutations.map(m => (
                      <div key={m.id} className="border border-border rounded overflow-hidden">
                        <div className="bg-surface px-3 py-1 text-xs font-medium text-white flex justify-between">
                          <span>{m.file_path}</span>
                          <span className="text-muted">{m.mutation_type}</span>
                        </div>
                        <div className="bg-black p-3 text-xs font-mono text-gray-300 overflow-x-auto whitespace-pre">
                          {m.diff_hunk}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                <div className="flex justify-end pt-2 border-t border-border mt-2">
                  <button className="bg-accent/10 hover:bg-accent/20 text-accent border border-accent/20 px-4 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-2">
                    <GitMerge className="w-4 h-4" /> Create Pull Request
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
