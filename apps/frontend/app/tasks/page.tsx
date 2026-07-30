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
        <h1 className="text-[clamp(32px,3vw,44px)] font-semibold tracking-tight text-slate-900 mb-2 leading-tight">Runs & History</h1>
        <p className="text-slate-500">View past task executions, plans, and AI modifications.</p>
      </div>

      <div className="relative mb-6 w-full md:max-w-md">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input 
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search intents..."
          className="w-full bg-white border border-forge-line rounded-xl pl-10 pr-4 h-[42px] text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
        />
      </div>

      <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-forge-line shadow-sm overflow-hidden">
        <div className="grid grid-cols-12 gap-4 p-4 md:px-6 border-b border-slate-200/60 text-[11px] font-semibold uppercase tracking-widest text-slate-500 bg-slate-50/50">
          <div className="col-span-12 md:col-span-7">Intent</div>
          <div className="col-span-4 md:col-span-2 hidden md:block">Status</div>
          <div className="col-span-4 md:col-span-2 hidden md:block">Date</div>
          <div className="col-span-1 hidden md:block text-right"></div>
        </div>
        
        <div className="divide-y divide-slate-100/80">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-32 text-slate-500 gap-4">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
              <span className="font-medium text-sm">Loading run history...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-slate-400">
              <Activity className="w-10 h-10 mb-4 text-slate-300" />
              <p className="font-medium text-sm">No runs found matching your search.</p>
            </div>
          ) : (
            filtered.map(run => (
              <Link href={`/tasks/${run.id}`} key={run.id} className="grid grid-cols-12 gap-4 p-4 md:px-6 hover:bg-slate-50/80 transition-colors items-center group block">
                <div className="col-span-12 md:col-span-7 flex items-start gap-3 md:gap-4">
                  <div className={`mt-0.5 w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${run.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-600 border border-emerald-100' : run.status === 'APPROVED' ? 'bg-blue-50 text-blue-600 border border-blue-100' : 'bg-amber-50 text-amber-600 border border-amber-100'}`}>
                    {run.status === 'COMPLETED' ? <GitCommit className="w-4 h-4" /> : <Activity className="w-4 h-4" />}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium text-[15px] text-slate-900 line-clamp-1 group-hover:text-blue-700 transition-colors" title={run.intent}>{run.intent}</div>
                    <div className="font-mono text-[10px] text-slate-400 mt-1 uppercase tracking-wider">{run.id.substring(0, 8)}</div>
                    <div className="mt-2 md:hidden flex gap-2">
                      <Badge variant={run.status === 'COMPLETED' ? 'success' : run.status === 'APPROVED' ? 'default' : 'warning'} className="text-[10px] px-2 py-0 h-5">
                        {run.status}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="col-span-2 hidden md:block">
                  <Badge variant={run.status === 'COMPLETED' ? 'success' : run.status === 'APPROVED' ? 'default' : 'warning'} className="text-[10px] px-2 py-0 h-5">
                    {run.status.replace('_', ' ')}
                  </Badge>
                </div>
                <div className="col-span-2 hidden md:flex items-center gap-1.5 text-[13px] font-mono text-slate-500">
                  <Clock className="w-3.5 h-3.5 opacity-70" />
                  {new Date(run.created_at).toLocaleDateString()}
                </div>
                <div className="col-span-1 hidden md:flex justify-end text-slate-300 group-hover:text-blue-600 transition-colors group-hover:translate-x-1 duration-200">
                  <ArrowRight className="w-4 h-4" />
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </AppShell>
  );
}
