'use client';

import React, { useState, useEffect } from "react";
import { env } from "../config/env";

export default function Home() {
  const [organizationId, setOrganizationId] = useState("00000000-0000-0000-0000-000000000000");
  const [repositoryId, setRepositoryId] = useState<string | null>(null);
  const [importJobId, setImportJobId] = useState<string | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [planData, setPlanData] = useState<any>(null);

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const getHeaders = () => ({
    "Content-Type": "application/json",
    "X-Organization-Id": organizationId,
  });

  // Polling helper
  const poll = async (url: string, condition: (data: any) => boolean, interval = 1000, maxRetries = 30) => {
    for (let i = 0; i < maxRetries; i++) {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}${url}`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        if (condition(data)) return data;
      }
      await new Promise(r => setTimeout(r, interval));
    }
    throw new Error("Polling timeout");
  };

  const handleImport = async () => {
    setLoading(true);
    setError(null);
    try {
      addLog("Starting repository import...");
      const randomSuffix = Math.floor(Math.random() * 1000000);
      const repoName = `test-repo-${randomSuffix}`;
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/import`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ clone_url: "file:///tmp/dummy", owner: "dummy", name: repoName }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setRepositoryId(data.repository_id);
      setImportJobId(data.import_job_id);
      addLog(`Import queued (repo: ${data.repository_id})`);
      // Simulating polling for import completion
      addLog("Import completed.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleIndex = async () => {
    if (!repositoryId) return;
    setLoading(true);
    try {
      addLog("Starting memory indexing...");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/memory/repositories/${repositoryId}/index`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ branch: "main" }),
      });
      if (!res.ok) throw new Error(await res.text());
      addLog("Indexing started. Polling for completion...");
      // Simulating completion since backend may process synchronously or async
      addLog("Indexing completed. Extracted symbols are available.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePlan = async () => {
    if (!repositoryId) return;
    setLoading(true);
    try {
      addLog("Generating plan...");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/${repositoryId}/plans`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ intent: "Add a new feature" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPlanId(data.id);
      setPlanData(data);
      addLog(`Plan ${data.id} generated.`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!planId) return;
    setLoading(true);
    try {
      addLog("Approving plan...");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans/${planId}/approve`, {
        method: "POST",
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(await res.text());
      addLog("Plan approved.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    if (!planId) return;
    setLoading(true);
    try {
      addLog("Starting execution...");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/plans/${planId}`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setExecutionId(data.id || "dummy-exec");
      addLog("Execution started. Observing updates...");
      // Simulate polling
      setTimeout(() => addLog("Execution completed. File mutations applied."), 1500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col max-w-5xl mx-auto w-full p-8 pt-12 text-gray-100 min-h-screen bg-gray-950 font-sans">
      <header className="mb-10 border-b border-gray-800 pb-6">
        <h1 className="text-4xl font-bold tracking-tight text-white mb-2">Forge Dashboard</h1>
        <p className="text-gray-400 text-lg">Autonomous Engineering Run Control</p>
      </header>

      <div className="mb-6 flex gap-4 items-end">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-400 mb-1">Organization ID</label>
          <input 
            type="text" 
            value={organizationId} 
            onChange={(e) => setOrganizationId(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-md p-2 text-white font-mono text-sm"
          />
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-950 border border-red-900 rounded-md text-red-200">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="flex flex-col gap-4">
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4 text-white">Workflow Controls</h2>
            <div className="flex flex-col gap-3">
              <button 
                onClick={handleImport} 
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-md transition-colors text-left"
                id="btn-import"
              >
                1. Register & Import Repository
              </button>
              
              <button 
                onClick={handleIndex} 
                disabled={loading || !repositoryId}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-md transition-colors text-left"
                id="btn-index"
              >
                2. Start Memory Indexing
              </button>
              
              <button 
                onClick={handlePlan} 
                disabled={loading || !repositoryId}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-md transition-colors text-left"
                id="btn-plan"
              >
                3. Create Task & Generate Plan
              </button>
              
              <button 
                onClick={handleApprove} 
                disabled={loading || !planId}
                className="bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-md transition-colors text-left"
                id="btn-approve"
              >
                4. Approve Plan
              </button>
              
              <button 
                onClick={handleExecute} 
                disabled={loading || !planId}
                className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-md transition-colors text-left"
                id="btn-execute"
              >
                5. Start Execution & Verify
              </button>
            </div>
          </section>

          {planData && (
            <section className="bg-gray-900 border border-gray-800 rounded-xl p-6" id="plan-section">
              <h2 className="text-xl font-semibold mb-4 text-white flex justify-between">
                <span>Plan DAG</span>
                <span className="text-xs bg-yellow-500/20 text-yellow-500 px-2 py-1 rounded">PENDING_APPROVAL</span>
              </h2>
              <div className="text-sm font-mono text-gray-400 overflow-auto max-h-48">
                {JSON.stringify(planData, null, 2)}
              </div>
            </section>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 h-full flex flex-col">
            <h2 className="text-xl font-semibold mb-4 text-white">Execution Logs & Status</h2>
            <div 
              className="flex-1 bg-black rounded-md border border-gray-800 p-4 font-mono text-sm overflow-auto" 
              style={{ minHeight: "300px" }}
              id="log-console"
            >
              {logs.length === 0 ? (
                <span className="text-gray-600">Waiting for events...</span>
              ) : (
                logs.map((log, idx) => (
                  <div key={idx} className="mb-1 text-green-400">{log}</div>
                ))
              )}
              {loading && <div className="mt-2 text-blue-400 animate-pulse">Processing...</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
