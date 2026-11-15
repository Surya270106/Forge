"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "../components/AppShell";
import "./bench.css";

type Task = { id: string; title: string; category: string; difficulty: string; instruction: string; budget_seconds: number };
type Suite = { id: string; version: number; name: string; dataset_digest: string; tasks: Task[] };
type Run = { id: string; status: string; created_at: string; dataset_digest: string; score?: number | null; pass_count?: number; trial_count?: number };

const headers = () => ({ "X-Organization-Id": localStorage.getItem("forge_org_id") || "" });

async function readJson(response: Response) {
  if (!response.ok) throw new Error(response.status === 403 ? "You do not have access to Forge Bench in this workspace." : "Forge Bench is unavailable. Check the API and your workspace session.");
  return response.json();
}

export default function BenchPage() {
  const router = useRouter();
  const [suite, setSuite] = useState<Suite | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(1);
  const [baseline, setBaseline] = useState("");
  const [budget, setBudget] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const requestKey = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const init = async () => {
      try {
        const suites = await readJson(await fetch("/api/v1/bench/suites", { headers: headers(), signal: controller.signal }));
        const first = suites.suites?.[0];
        if (!first) { setError("No benchmark suite is available."); return; }
        const [detail, history] = await Promise.all([
          fetch(`/api/v1/bench/suites/${first.id}`, { headers: headers(), signal: controller.signal }).then(readJson),
          fetch("/api/v1/bench/runs", { headers: headers(), signal: controller.signal }).then(readJson),
        ]);
        if (controller.signal.aborted) return;
        setSuite(detail); setSelected(detail.tasks.map((task: Task) => task.id));
        const recent: Run[] = history.runs || [];
        setRuns(recent);
        if (recent[0]) {
          const latest = await fetch(`/api/v1/bench/runs/${recent[0].id}`, { headers: headers(), signal: controller.signal }).then(readJson);
          if (!controller.signal.aborted) setRuns([latest, ...recent.slice(1)]);
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Forge Bench could not load.");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void init();
    return () => controller.abort();
  }, []);

  const toggle = (id: string) => { requestKey.current = null; setSelected((current) => current.includes(id) ? current.filter((task) => task !== id) : [...current, id]); };

  const createRun = async () => {
    if (!suite || !selected.length || selected.length * repetitions > 24 || submitting) return;
    setSubmitting(true); setError("");
    requestKey.current ||= crypto.randomUUID();
    try {
      const run = await readJson(await fetch("/api/v1/bench/runs", {
        method: "POST", headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ suite_id: suite.id, task_ids: selected, repetitions,
          baseline_run_id: baseline || null, budget_seconds: budget || null, idempotency_key: requestKey.current }),
      }));
      requestKey.current = null;
      router.push(`/bench/${run.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The benchmark run could not start.");
    } finally { setSubmitting(false); }
  };

  const latest = runs[0];
  return <AppShell><div className="page-frame bench-page">
    <header className="page-intro">
      <div className="section-label"><span>04</span>Forge Bench</div>
      <h1>Measure the<br />work, not the words.</h1>
      <p>Run coding tasks through Forge’s local worker and grade the exact resulting patch with independent tests.</p>
    </header>
    <p className="bench-notice">Infrastructure demo: the deterministic planner makes no paid model calls. These scores measure the execution and grading pipeline, not model intelligence. A Docker-capable worker is required.</p>
    {error && <p className="product-alert" role="alert">{error}</p>}
    {loading ? <div className="data-state"><span className="loading-orbit" />Loading benchmark suites</div> : !suite ?
      <div className="data-state">No suite is available.</div> : <>
      <section className="bench-summary" aria-label="Benchmark overview">
        <div><span>Suite</span><strong>{suite.name}</strong><small>v{suite.version} · {suite.tasks.length} tasks</small></div>
        <div><span>Last run</span><strong>{latest?.status || "None"}</strong><small>{latest ? new Date(latest.created_at).toLocaleString() : "Start the first evaluation"}</small></div>
        <div><span>Latest score</span><strong>{latest?.score == null ? "—" : `${latest.score}/100`}</strong><small>{latest?.trial_count ? `${latest.pass_count || 0}/${latest.trial_count} passed` : "No scored trials"}</small></div>
      </section>
      <section className="bench-create" aria-labelledby="bench-create-title">
        <div className="bench-section-heading"><div><span className="section-label">01 / Configure</span><h2 id="bench-create-title">New evaluation</h2></div><span>{selected.length} tasks selected</span></div>
        <div className="bench-task-list">
          {suite.tasks.map((task) => <label className="bench-task" key={task.id}>
            <input type="checkbox" checked={selected.includes(task.id)} onChange={() => toggle(task.id)} />
            <span><strong>{task.title}</strong><small>{task.category.replaceAll("_", " ")} · {task.difficulty} · {task.budget_seconds}s budget</small><em>{task.instruction}</em></span>
          </label>)}
        </div>
        <div className="bench-controls">
          <label>Repetitions<select value={repetitions} onChange={(event) => { requestKey.current = null; setRepetitions(Number(event.target.value)); }}>{[1, 2, 3].map((count) => <option key={count} value={count}>{count}</option>)}</select></label>
          <label>Execution budget<select value={budget} onChange={(event) => { requestKey.current = null; setBudget(Number(event.target.value)); }}><option value={0}>Task default</option>{[30, 60, 120, 180].map((seconds) => <option key={seconds} value={seconds}>{seconds} seconds maximum</option>)}</select></label>
          <label>Baseline<select value={baseline} onChange={(event) => { requestKey.current = null; setBaseline(event.target.value); }}><option value="">No baseline</option>{runs.filter((run) => run.dataset_digest === suite.dataset_digest).map((run) => <option value={run.id} key={run.id}>{run.id.slice(0, 8)} · {run.status}</option>)}</select></label>
          <button type="button" className="button" disabled={!selected.length || selected.length * repetitions > 24 || submitting} onClick={() => void createRun()}>{submitting ? "Creating run…" : "Start local evaluation →"}</button>
        </div>
        {selected.length * repetitions > 24 && <p className="product-alert">A run is limited to 24 trials. Select fewer tasks or repetitions.</p>}
      </section>
      <section className="bench-history" aria-labelledby="bench-history-title">
        <div className="bench-section-heading"><div><span className="section-label">02 / Evidence</span><h2 id="bench-history-title">Recent runs</h2></div></div>
        {runs.length ? runs.map((run) => <Link className="bench-history-row" href={`/bench/${run.id}`} key={run.id}><strong>{run.id.slice(0, 8)}</strong><span>{run.status}</span><time>{new Date(run.created_at).toLocaleString()}</time><b>↗</b></Link>) : <div className="data-state">No benchmark runs yet.</div>}
      </section>
    </>}
  </div></AppShell>;
}
