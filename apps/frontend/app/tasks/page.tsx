'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Activity, Clock, Search, ArrowRight, Loader2, GitCommit } from "lucide-react";
import Link from "next/link";

export default function RunsPage() {
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const fetchRuns = async () => {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Organization-Id": orgId || ""
          }
        });
        if (res.ok) {
          const data = await res.json();
          setRuns(data.plans || []);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchRuns();
  }, []);

  const filtered = runs.filter(r => (r.intent || "").toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="p-8 max-w-5xl mx-auto flex flex-col h-full">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Runs & History</h1>
        <p className="text-muted">View past task executions, plans, and AI modifications.</p>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 mb-6 flex items-center gap-4 shrink-0">
        <Search className="w-5 h-5 text-muted" />
        <input 
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search intents or repositories..."
          className="flex-1 bg-transparent border-none focus:outline-none text-white"
        />
      </div>

      <div className="flex-1 overflow-hidden flex flex-col bg-surface border border-border rounded-xl">
        <div className="grid grid-cols-12 gap-4 p-4 border-b border-border text-sm font-medium text-muted bg-black/20 shrink-0">
          <div className="col-span-5">Intent</div>
          <div className="col-span-3">Status</div>
          <div className="col-span-3">Date</div>
          <div className="col-span-1 text-right">Action</div>
        </div>
        
        <div className="overflow-y-auto flex-1 p-2">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted gap-3">
              <Loader2 className="w-5 h-5 animate-spin" /> Loading run history...
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted">
              <Activity className="w-12 h-12 mb-4 opacity-50" />
              <p>No runs found matching your search.</p>
            </div>
          ) : (
            filtered.map(run => (
              <Link href={`/tasks/${run.id}`} key={run.id} className="grid grid-cols-12 gap-4 p-4 hover:bg-black/40 rounded-lg transition-colors items-center group">
                <div className="col-span-5 flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${run.status === 'COMPLETED' ? 'bg-green-900/30 text-green-400' : run.status === 'APPROVED' ? 'bg-blue-900/30 text-blue-400' : 'bg-yellow-900/30 text-yellow-400'}`}>
                    {run.status === 'COMPLETED' ? <GitCommit className="w-4 h-4" /> : <Activity className="w-4 h-4" />}
                  </div>
                  <div className="truncate font-medium text-white" title={run.intent}>{run.intent}</div>
                </div>
                <div className="col-span-3">
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider ${run.status === 'COMPLETED' ? 'bg-green-900/30 text-green-400 border border-green-900/50' : run.status === 'APPROVED' ? 'bg-blue-900/30 text-blue-400 border border-blue-900/50' : 'bg-yellow-900/30 text-yellow-400 border border-yellow-900/50'}`}>
                    {run.status}
                  </span>
                </div>
                <div className="col-span-3 flex items-center gap-2 text-sm text-muted">
                  <Clock className="w-3.5 h-3.5" />
                  {new Date(run.created_at).toLocaleDateString()}
                </div>
                <div className="col-span-1 flex justify-end text-muted group-hover:text-accent transition-colors">
                  <ArrowRight className="w-4 h-4" />
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
