"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "../../components/AppShell";
import "../bench.css";

type Check = { id: string; category: string; status: string; duration_ms: number; exit_code: number | null };
type Result = { score: number; passed: boolean; checks: Check[]; breakdown: Record<string, number | null>; metrics: Record<string, number | string | null>; patch_digest: string };
type Trial = { id: string; task_id: string; repetition: number; status: string; plan_id: string | null; execution_id: string | null; failure_category: string | null; base_commit: string; result: Result | null };
type Run = { id: string; status: string; score: number | null; score_denominator: number; pass_count: number; trial_count: number; infrastructure_error_count: number; cancelled_count: number; dataset_digest: string; manifest: { mode: string; tasks: { id: string }[] }; trials: Trial[] };
type Comparison = { left: Run; right: Run; delta: { score_delta: number | null; pass_rate_delta: number | null; duration_ms_delta: number | null; token_count_delta: number | null; dimension_deltas: Record<string, number | null> } };

const headers = () => ({ "X-Organization-Id": localStorage.getItem("forge_org_id") || "" });

export default function BenchRunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<{ id: string; dataset_digest: string }[]>([]);
  const [comparisonId, setComparisonId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const response = await fetch(`/api/v1/bench/runs/${id}`, { headers: headers(), signal });
    if (!response.ok) throw new Error(response.status === 404 ? "This run is unavailable in the selected workspace." : "Run status could not be loaded.");
    setRun(await response.json());
  }, [id]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      refresh(controller.signal),
      fetch("/api/v1/bench/runs", { headers: headers(), signal: controller.signal }).then(async (response) => {
        if (response.ok) setHistory((await response.json()).runs || []);
      }),
    ]).catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Run status is unavailable."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    const timer = window.setInterval(() => { void refresh(controller.signal).catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Run status is unavailable."); }); }, 3000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [refresh]);

  const cancel = async () => {
    setError("");
    try {
      const response = await fetch(`/api/v1/bench/runs/${id}/cancel`, { method: "POST", headers: headers() });
      if (!response.ok) throw new Error("Cancellation could not be requested.");
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Cancellation failed."); }
  };

  const compare = async (other: string) => {
    setComparisonId(other); setComparison(null); setError("");
    if (!other) return;
    try {
      const response = await fetch(`/api/v1/bench/compare?left=${id}&right=${other}`, { headers: headers() });
      if (!response.ok) throw new Error(response.status === 422 ? "These runs used different tasks or dataset versions." : "Comparison could not be loaded.");
      setComparison(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Comparison failed."); }
  };

  return <AppShell><div className="page-frame bench-page">
    <header className="page-intro"><div className="section-label"><span>04</span>Forge Bench / Run</div><h1>Evidence for<br />every trial.</h1><p>Each result comes from a real Forge execution and independent Docker grading. This deterministic demo does not measure model intelligence.</p></header>
    <p><Link href="/bench">← All benchmark runs</Link></p>
    {error && <p className="product-alert" role="alert">{error}</p>}
    {loading ? <div className="data-state"><span className="loading-orbit" />Loading run evidence</div> : !run ? <div className="data-state">Run unavailable.</div> : <>
      <section className="bench-summary" aria-label="Run summary">
        <div><span>Status</span><strong>{run.status}</strong><small>{run.id.slice(0, 8)}</small></div>
        <div><span>Overall score</span><strong>{run.score == null ? "—" : `${run.score}/100`}</strong><small>{run.score_denominator} agent trials counted; infrastructure errors excluded</small></div>
        <div><span>Passed</span><strong>{run.pass_count}/{run.trial_count}</strong><small>{run.infrastructure_error_count} infrastructure errors · {run.cancelled_count} cancelled</small></div>
      </section>
      <p className="bench-notice">Dataset SHA-256: <code>{run.dataset_digest}</code>. Scoring weights: correctness 45%, regression 20%, patch quality 10%, reliability 10%, efficiency 10%, safety 5%. Missing evidence is shown as unavailable; failed required checks cap the score below 50.</p>
      <div className="bench-controls">
        {!["COMPLETED", "CANCELLED", "FAILED"].includes(run.status) && <button type="button" className="button" onClick={() => void cancel()}>Cancel remaining trials</button>}
        <a className="button" href={`/api/v1/bench/runs/${id}/export`}>Export JSON</a>
        <label>Compare with<select value={comparisonId} onChange={(event) => void compare(event.target.value)}><option value="">Select a compatible run</option>{history.filter((other) => other.id !== id && other.dataset_digest === run.dataset_digest).map((other) => <option value={other.id} key={other.id}>{other.id.slice(0, 8)}</option>)}</select></label>
      </div>
      {comparison && <section className="bench-notice" aria-label="Run comparison"><strong>Comparison:</strong> {comparison.left.score ?? "—"} → {comparison.right.score ?? "—"} points ({comparison.delta.score_delta == null ? "unavailable" : `${comparison.delta.score_delta >= 0 ? "+" : ""}${comparison.delta.score_delta}`}); {comparison.left.pass_count}/{comparison.left.trial_count} → {comparison.right.pass_count}/{comparison.right.trial_count} passed. Duration change: {comparison.delta.duration_ms_delta ?? "unavailable"} ms; token change: {comparison.delta.token_count_delta ?? "unavailable"}. <span className="bench-breakdown">{Object.entries(comparison.delta.dimension_deltas).map(([dimension, delta]) => <span key={dimension}>{dimension}: {delta == null ? "unavailable" : `${delta >= 0 ? "+" : ""}${delta}`}</span>)}</span>Small samples do not establish statistical superiority.</section>}
      <section aria-label="Benchmark trials"><div className="bench-section-heading"><div><span className="section-label">Trial evidence</span><h2>Recorded outcomes</h2></div></div>
        {run.trials.map((trial) => <article className="bench-trial" key={trial.id}>
          <header><div><h3>{trial.task_id.replaceAll("-", " ")} · #{trial.repetition}</h3><small>Base {trial.base_commit.slice(0, 12)} · {trial.status}</small></div><strong>{trial.result ? `${trial.result.score}/100` : "—"}</strong></header>
          {trial.failure_category && <p>Failure category: {trial.failure_category}</p>}
          {trial.plan_id && <p><Link href={`/tasks/${trial.plan_id}`}>Open execution and Flight Recorder →</Link></p>}
          {trial.result && <><p>Patch SHA-256: <code>{trial.result.patch_digest}</code></p><ul className="bench-checks">{trial.result.checks.map((check) => <li key={check.id}><span>{check.id} · {check.category}</span><strong className={check.status}>{check.status} · {check.duration_ms} ms</strong></li>)}</ul><div className="bench-breakdown">{Object.entries(trial.result.breakdown).map(([name, value]) => <span key={name}>{name}: {value == null ? "unavailable" : `${Math.round(value)}%`}</span>)}</div><p>Duration: {trial.result.metrics.duration_ms ?? "unavailable"} ms · Tokens: {trial.result.metrics.token_count ?? "unavailable"} · Retries: {trial.result.metrics.retry_count ?? "unavailable"}</p></>}
        </article>)}
      </section>
    </>}
  </div></AppShell>;
}
