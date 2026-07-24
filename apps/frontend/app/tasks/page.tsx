'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../config/env";
import { Activity, Clock, Search, ArrowRight, Loader2, GitCommit } from "lucide-react";
import Link from "next/link";
import { AppShell } from "../components/AppShell";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";

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
    <AppShell>
      <div className="mb-8">
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-2">Runs & History</h1>
        <p className="text-slate-500">View past task executions, plans, and AI modifications.</p>
      </div>

      <div className="relative mb-6">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
        <input 
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search intents..."
          className="w-full bg-white border border-slate-200 rounded-xl pl-12 pr-4 py-3 text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
        />
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-12 gap-4 p-4 border-b border-slate-100 text-xs font-semibold uppercase tracking-wider text-slate-500 bg-slate-50/50 font-mono">
          <div className="col-span-12 md:col-span-6">Intent</div>
          <div className="col-span-4 md:col-span-2 hidden md:block">Status</div>
          <div className="col-span-4 md:col-span-3 hidden md:block">Date</div>
          <div className="col-span-1 hidden md:block text-right"></div>
        </div>
        
        <div className="divide-y divide-slate-100">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 text-slate-500 gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
              <span className="font-medium">Loading run history...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-slate-400">
              <Activity className="w-12 h-12 mb-4 text-slate-300" />
              <p>No runs found matching your search.</p>
            </div>
          ) : (
            filtered.map(run => (
              <Link href={`/tasks/${run.id}`} key={run.id} className="grid grid-cols-12 gap-4 p-4 hover:bg-slate-50 transition-colors items-center group block">
                <div className="col-span-12 md:col-span-6 flex items-start gap-4">
                  <div className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${run.status === 'COMPLETED' ? 'bg-green-50 text-green-600' : run.status === 'APPROVED' ? 'bg-blue-50 text-blue-600' : 'bg-yellow-50 text-yellow-600'}`}>
                    {run.status === 'COMPLETED' ? <GitCommit className="w-4 h-4" /> : <Activity className="w-4 h-4" />}
                  </div>
                  <div>
                    <div className="font-medium text-slate-900 line-clamp-2" title={run.intent}>{run.intent}</div>
                    <div className="mt-1 md:hidden flex gap-2">
                      <Badge variant={run.status === 'COMPLETED' ? 'success' : run.status === 'APPROVED' ? 'default' : 'warning'}>
                        {run.status}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="col-span-2 hidden md:block">
                  <Badge variant={run.status === 'COMPLETED' ? 'success' : run.status === 'APPROVED' ? 'default' : 'warning'}>
                    {run.status.replace('_', ' ')}
                  </Badge>
                </div>
                <div className="col-span-3 hidden md:flex items-center gap-2 text-sm text-slate-500">
                  <Clock className="w-3.5 h-3.5" />
                  {new Date(run.created_at).toLocaleDateString()}
                </div>
                <div className="col-span-1 hidden md:flex justify-end text-slate-300 group-hover:text-blue-500 transition-colors">
                  <ArrowRight className="w-4 h-4" />
                </div>
              </Link>
            ))
          )}
        </div>
      </Card>
    </AppShell>
  );
}
