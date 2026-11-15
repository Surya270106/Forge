"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "../../components/AppShell";

type Repository = { id: string; name: string; owner: string; status: string; default_branch: string; indexing_status?: string; indexing_progress?: number };
type Plan = { id: string; repository_id: string; intent: string; status: string; created_at: string };
type Tab = "overview" | "memory" | "plans" | "runs";

export default function RepositoryDetailPage() {
  const repositoryId = useParams().id as string;
  const router = useRouter();
  const [repository, setRepository] = useState<Repository | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [intent, setIntent] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const headers = useCallback(() => ({ "X-Organization-Id": localStorage.getItem("forge_org_id") || "" }), []);
  const fetchRepository = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/repositories/imported`, { headers: headers() });
      if (response.ok) { const data = await response.json(); setRepository((data.repositories || []).find((repo: Repository) => repo.id === repositoryId) || null); }
    } catch (error) { console.error(error); }
  }, [headers, repositoryId]);
  const fetchPlans = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/plans`, { headers: headers() });
      if (response.ok) { const data = await response.json(); setPlans((data.plans || []).filter((plan: Plan) => plan.repository_id === repositoryId)); }
    } catch (error) { console.error(error); }
  }, [headers, repositoryId]);
  useEffect(() => {
    Promise.all([fetchRepository(), fetchPlans()]).finally(() => setLoading(false));
    const interval = window.setInterval(() => { void fetchRepository(); void fetchPlans(); }, 5000);
    return () => window.clearInterval(interval);
  }, [fetchPlans, fetchRepository]);
  const indexRepository = async () => {
    if (!repository) return; setActionLoading(true);
    try {
      const response = await fetch(`/api/v1/memory/repositories/${repositoryId}/index`, {
        method: "POST", headers: { ...headers(), "Content-Type": "application/json" }, body: JSON.stringify({ branch: repository.default_branch || "main" }),
      });
      if (!response.ok) throw new Error("Index failed");
      setActiveTab("memory"); await fetchRepository();
    } catch (error) { console.error(error); window.alert("Failed to start indexing."); } finally { setActionLoading(false); }
  };
  const createPlan = async () => {
    if (!intent.trim()) return; setActionLoading(true);
    try {
      const response = await fetch(`/api/v1/repositories/${repositoryId}/plans`, {
        method: "POST", headers: { ...headers(), "Content-Type": "application/json" }, body: JSON.stringify({ intent }),
      });
      if (response.ok) { const plan = await response.json(); router.push(`/tasks/${plan.id}`); return; }
      const error = await response.json().catch(() => ({})); window.alert(`Failed to create plan: ${error.detail || error.message || response.status}`);
    } catch (error) { console.error(error); window.alert("Failed to create plan."); } finally { setActionLoading(false); }
  };
  if (loading) return <AppShell><div className="data-state full-page-state"><span className="loading-orbit" />Reading repository context</div></AppShell>;
  if (!repository) return <AppShell><div className="data-state full-page-state">Repository not found.</div></AppShell>;

  const pending = plans.filter((plan) => plan.status === "PENDING_APPROVAL");
  const indexState = repository.indexing_status || "NOT_STARTED";
  const indexing = ["PENDING", "SCANNING", "PARSING"].includes(indexState);
  return (
    <AppShell><div className="page-frame">
      <Link href="/" className="back-link"><span>←</span> Workspace</Link>
      <header className="repository-header">
        <div><p className="eyebrow repository-eyebrow"><span />Repository context</p><h1>{repository.name}</h1></div>
        <div className="repository-meta">
          <span><i>Owner</i><strong>{repository.owner}</strong></span>
          <span><i>Branch</i><strong>{repository.default_branch || "main"}</strong></span>
          <span><i>State</i><strong className={`status-${repository.status.toLowerCase()}`}>{repository.status}</strong></span>
        </div>
      </header>
      <nav className="segment-nav" aria-label="Repository sections">
        {([["overview", "Task"], ["memory", "Memory"], ["plans", `Plans ${String(plans.length).padStart(2, "0")}`], ["runs", "Runs"]] as [Tab, string][]).map(([tab, label], index) => (
          <button type="button" className={activeTab === tab ? "is-active" : ""} onClick={() => setActiveTab(tab)} key={tab}><span>{String(index + 1).padStart(2, "0")}</span>{label}</button>
        ))}
      </nav>
      {activeTab === "overview" && (
        <section className="workbench-panel">
          <div className="workbench-copy"><span>New engineering task</span><h2>Describe the outcome, not the implementation.</h2><p>Forge will use repository memory to turn your intent into a reviewable plan before it changes a file.</p>
            <div className="workbench-stats"><span><i>Pending plans</i><strong>{String(pending.length).padStart(2, "0")}</strong></span><span><i>Memory</i><strong>{indexState.replaceAll("_", " ")}</strong></span></div>
          </div>
          <div className="intent-console"><label htmlFor="forge-intent">Intent</label><textarea id="forge-intent" value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="Add a rate limit to the authentication middleware and verify the existing login flow." rows={7} />
            <div><code>Repository / {repository.owner}/{repository.name}</code><button type="button" className="button button-white" disabled={actionLoading || !intent.trim() || repository.status !== "READY"} onClick={createPlan}>{actionLoading ? "Planning…" : "Generate plan"} <span>→</span></button></div>
          </div>
        </section>
      )}
      {activeTab === "memory" && (
        <section className="focus-panel"><div className="section-label"><span>02</span>Repository memory</div><div>
          <span className={`focus-state status-${indexState.toLowerCase()}`}>
            {indexing ? (repository.indexing_progress ? `Indexing in progress (${repository.indexing_progress}%)` : "Indexing in progress") : indexState.replaceAll("_", " ")}
          </span>
          <h2>{indexState === "COMPLETED" ? "The repository is mapped and ready." : indexState === "FAILED" ? "The last indexing pass did not complete." : indexing ? "Forge is reading structure and dependencies." : "Build context before asking Forge to plan."}</h2>
          <p>Indexing prepares file structure, language, framework, and dependency evidence for the planning engine.</p>
          <button type="button" className="button button-primary" onClick={indexRepository} disabled={actionLoading || repository.status !== "READY"}>{actionLoading ? "Starting…" : indexState === "COMPLETED" ? "Re-index codebase" : "Index codebase"} <span>→</span></button>
        </div></section>
      )}
      {activeTab === "plans" && (
        <section className="data-ledger detail-ledger">
          <div className="data-ledger-head plan-ledger-grid"><span>Intent</span><span>Status</span><span>Created</span><span>Review</span></div>
          {plans.length === 0 ? <div className="data-state">No plans have been created for this repository.</div> : plans.map((plan, index) => (
            <Link href={`/tasks/${plan.id}`} className="data-row plan-ledger-grid run-row" key={plan.id}>
              <div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{plan.intent}</h2><p>{plan.id.slice(0, 8).toUpperCase()}</p></div></div>
              <span className={`status-ink status-${plan.status.toLowerCase()}`}>{plan.status.replaceAll("_", " ")}</span><time>{new Date(plan.created_at).toLocaleDateString()}</time><b>↗</b>
            </Link>
          ))}
        </section>
      )}
      {activeTab === "runs" && (
        <section className="focus-panel compact-focus-panel"><div className="section-label"><span>04</span>Execution</div><div><span className="focus-state">Run evidence</span><h2>Execution begins after a plan is approved.</h2><p>Open a plan to start execution and inspect its logs, status, and captured file mutations.</p><Link className="button button-primary" href="/tasks">Open run history <span>→</span></Link></div></section>
      )}
    </div></AppShell>
  );
}
