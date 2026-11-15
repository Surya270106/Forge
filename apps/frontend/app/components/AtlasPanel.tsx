"use client";

import { useCallback, useEffect, useState } from "react";

type Snapshot = { id: string; commit_sha: string; dirty: boolean; stats: Record<string, number>; warnings: string[]; completed_at: string };
type Job = { id: string; status: string; error_code: string | null };
type Node = { id: string; key: string; kind: string; name: string; path: string | null };
type Evidence = { kind: string; source: string; target: string | null; evidence_path: string; evidence_line: number; confidence: string; resolution: string };
type Impact = { items: { key: string; depth: number; via: Evidence[] }[]; unresolved: Evidence[]; truncated: boolean };

export function AtlasPanel({ repositoryId, repositoryReady }: { repositoryId: string; repositoryReady: boolean }) {
  const base = `/api/v1/repositories/${repositoryId}/atlas`;
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [query, setQuery] = useState("");
  const [nodes, setNodes] = useState<Node[]>([]);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [tests, setTests] = useState<string[]>([]);
  const [chosen, setChosen] = useState("");
  const [comparison, setComparison] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await fetch(`${base}${path}`, {
      ...init,
      headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "", ...init?.headers },
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) throw new Error("Your session or workspace access has expired. Sign in again.");
      if (response.status === 503) throw new Error("Atlas is unavailable while the API is down.");
      throw new Error(`Atlas request failed (${response.status}).`);
    }
    return response.json();
  }, [base]);

  const refresh = useCallback(async () => {
    try {
      const data = await request("/snapshots?page_size=20");
      setSnapshots(data.items);
      setSelected((current) => current || data.items[0]?.id || "");
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Atlas is unavailable."); }
  }, [request]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next: Job = await request(`/jobs/${job.id}`);
        setJob(next);
        if (next.status === "SUCCEEDED") void refresh();
      } catch (cause) { setError(cause instanceof Error ? cause.message : "Job status is unavailable."); }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [job, refresh, request]);
  useEffect(() => { setNodes([]); setImpact(null); setTests([]); setChosen(""); setComparison([]); }, [selected]);

  const start = async () => {
    setBusy(true); setError("");
    try {
      setJob(await request("/index", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
      }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Indexing could not start."); }
    finally { setBusy(false); }
  };

  const search = async () => {
    if (!selected) return;
    setBusy(true); setError(""); setImpact(null); setTests([]);
    try {
      const data = await request(`/symbols?snapshot_id=${selected}&query=${encodeURIComponent(query)}&page_size=100`);
      setNodes(data.items);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Symbol search failed."); }
    finally { setBusy(false); }
  };

  const inspect = async (key: string) => {
    setBusy(true); setError(""); setChosen(key);
    try {
      const parameters = `snapshot_id=${selected}&node_key=${encodeURIComponent(key)}`;
      const [impactData, testData] = await Promise.all([request(`/impact?${parameters}`), request(`/tests?${parameters}`)]);
      setImpact(impactData);
      setTests(testData.items.map((item: { key: string }) => item.key));
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Impact analysis failed."); }
    finally { setBusy(false); }
  };

  const compare = async (older: string) => {
    setBusy(true); setError("");
    try {
      const data = await request(`/diff?left=${older}&right=${selected}`);
      setComparison([`Added: ${data.totals.added_nodes} nodes, ${data.totals.added_edges} relationships`,
        `Removed: ${data.totals.removed_nodes} nodes, ${data.totals.removed_edges} relationships`,
        `Changed: ${data.totals.changed_nodes} nodes`, `Renamed: ${data.totals.renamed_files} files`]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Snapshot comparison failed."); }
    finally { setBusy(false); }
  };

  const current = snapshots.find((item) => item.id === selected);
  return <section className="focus-panel"><div className="section-label"><span>03</span>Atlas</div><div>
    <span className="focus-state">Version-aware repository graph</span>
    <h2>Trace code relationships to their source.</h2>
    <p>Atlas maps imports, direct calls, and test associations. Unresolved relationships remain visible; these suggestions do not replace verification.</p>
    <p>Supported source: Python, JavaScript, TypeScript, and TSX.</p>
    {error && <p className="product-alert" role="alert">{error}</p>}
    <button type="button" className="button button-primary" onClick={start} disabled={busy || !repositoryReady || job?.status === "QUEUED" || job?.status === "RUNNING"}>Index current workspace</button>
    {job && <p role="status">Index job: {job.status}{job.error_code ? ` (${job.error_code})` : ""}</p>}
    {snapshots.length === 0 ? <p>No published Atlas snapshot yet. Indexing needs a running repository worker.</p> : <>
      <label htmlFor="atlas-snapshot">Published snapshot</label>
      <select id="atlas-snapshot" value={selected} onChange={(event) => setSelected(event.target.value)}>
        {snapshots.map((item) => <option key={item.id} value={item.id}>{item.commit_sha.slice(0, 10)}{item.dirty ? " · dirty workspace" : ""} · {new Date(item.completed_at).toLocaleString()}</option>)}
      </select>
      {current && <p>{current.stats.files} files · {current.stats.nodes} nodes · {current.stats.edges} relationships{current.warnings.length ? ` · ${current.warnings.length} warnings` : ""}</p>}
      {current?.warnings.length ? <details><summary>Indexing warnings</summary><ul>{current.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details> : null}
      <form onSubmit={(event) => { event.preventDefault(); void search(); }}>
        <label htmlFor="atlas-query">Find a symbol</label>
        <input id="atlas-query" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={100} placeholder="Function, class, or test name" />
        <button type="submit" disabled={busy}>Search</button>
      </form>
      {nodes.length > 0 && <ul>{nodes.map((node) => <li key={node.id}><button type="button" onClick={() => void inspect(node.key)} disabled={busy}>{node.name}</button> <small>{node.kind} · {node.path}</small></li>)}</ul>}
      {chosen && impact && <div aria-live="polite"><h3>Impact for {chosen}</h3>
        {impact.items.length === 0 && <p>No resolved downstream relationships in this snapshot.</p>}
        <ul>{impact.items.map((item) => <li key={item.key}>{item.key} · depth {item.depth}<ul>{item.via.map((edge, index) => <li key={`${edge.source}-${index}`}>{edge.kind} at {edge.evidence_path}:{edge.evidence_line} · {edge.resolution}, {edge.confidence}</li>)}</ul></li>)}</ul>
        {impact.unresolved.length > 0 && <p>{impact.unresolved.length} unresolved relationships require manual inspection.</p>}
        {tests.length > 0 && <p>Associated test files (inferred, not coverage): {tests.join(", ")}</p>}
        {impact.truncated && <p>Result limit reached. Narrow the query for more detail.</p>}
      </div>}
      {snapshots.length > 1 && <button type="button" onClick={() => void compare(snapshots.find((item) => item.id !== selected)!.id)} disabled={busy}>Compare with another snapshot</button>}
      {comparison.map((line) => <p key={line}>{line}</p>)}
    </>}
  </div></section>;
}
