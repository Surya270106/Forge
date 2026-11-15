"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "../components/AppShell";

type Plan = { id: string; intent: string; status: string; created_at: string };

export default function RunsPage() {
  const [runs, setRuns] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  useEffect(() => {
    fetch(`/api/v1/plans`, {
      headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "" },
    }).then(async (response) => { if (response.ok) { const data = await response.json(); setRuns(data.plans || []); } })
      .catch(console.error).finally(() => setLoading(false));
  }, []);
  const filtered = useMemo(() => runs.filter((run) => (run.intent || "").toLowerCase().includes(search.toLowerCase())), [runs, search]);
  return (
    <AppShell><div className="page-frame">
      <header className="page-intro">
        <div className="section-label"><span>03</span>Execution record</div>
        <h1>Every decision<br />stays inspectable.</h1>
        <p>Revisit a proposed plan, continue an approved execution, or inspect the evidence left by completed work.</p>
      </header>
      <div className="page-toolbar">
        <label className="search-field"><span>Filter intent</span><input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Describe the change you are looking for" /><i>⌕</i></label>
        <span className="toolbar-count">{loading ? "—" : String(filtered.length).padStart(2, "0")} records</span>
      </div>
      <section className="data-ledger" aria-label="Plans and execution history">
        <div className="data-ledger-head run-ledger-grid"><span>Intent</span><span>Status</span><span>Created</span><span>Open</span></div>
        {loading ? <div className="data-state"><span className="loading-orbit" />Reading execution history</div> :
          filtered.length === 0 ? <div className="data-state">No execution records match this search.</div> :
          filtered.map((run, index) => (
            <Link href={`/tasks/${run.id}`} className="data-row run-ledger-grid run-row" key={run.id}>
              <div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{run.intent}</h2><p>Plan {run.id.slice(0, 8).toUpperCase()}</p></div></div>
              <span className={`status-ink status-${run.status.toLowerCase()}`}>{run.status.replaceAll("_", " ")}</span>
              <time dateTime={run.created_at}>{new Date(run.created_at).toLocaleDateString()}</time><b>↗</b>
            </Link>
          ))}
      </section>
      <div className="page-note"><span>Forge record</span><p>Plans remain reviewable before execution. Logs and mutations remain visible after the run reaches a terminal state.</p></div>
    </div></AppShell>
  );
}
