"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "./AppShell";

type Workspace = { id: string; name: string };
type Repository = { id: string; owner: string; name: string; status: string; default_branch: string; indexing_status?: string };
type Plan = { id: string; repository_id: string; intent: string; status: string; created_at: string };
type Job = { id: string; status: string };
type Patch = { status: string; publish_status: string; pull_request_url: string | null };
type Task = Plan & { job?: Job; jobUnavailable?: boolean; verification?: string; verificationUnavailable?: boolean; patch?: Patch };
type Dashboard = { workspace: Workspace | null; repositories: Repository[]; tasks: Task[]; providerState: "configured" | "missing" | "unknown"; github: "connected" | "missing" | "unknown" };

async function request<T>(url: string, headers?: HeadersInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { headers, signal, cache: "no-store" });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
}

function stateOf(task: Task): string {
  if (task.patch?.publish_status === "SUCCEEDED") return "Published";
  if (task.patch?.publish_status === "FAILED") return "Publication failed";
  if (["QUEUED", "RUNNING"].includes(task.patch?.publish_status || "")) return "Publishing";
  if (task.patch?.status === "GENERATED") return "Review changes";
  if (task.verification === "FAILED") return "Verification failed";
  if (task.verification === "PASSED") return "Verified";
  if (task.job?.status === "FAILED") return "Execution failed";
  if (task.job?.status === "RUNNING") return "Running";
  if (task.job?.status === "PENDING") return "Queued";
  if (task.jobUnavailable || task.verificationUnavailable) return "Execution status unavailable";
  if (task.job?.status === "COMPLETED") return "Awaiting verification";
  if (task.status === "PENDING_APPROVAL") return "Approve plan";
  if (task.status === "APPROVED") return "Ready to execute";
  return task.status.replaceAll("_", " ").toLowerCase();
}

const attentionStates = new Set(["Approve plan", "Execution failed", "Verification failed", "Review changes", "Publication failed"]);

export default function ProductDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const { workspaces } = await request<{ workspaces: Workspace[] }>("/api/v1/auth/workspaces", undefined, controller.signal);
        const saved = localStorage.getItem("forge_org_id");
        const workspace = workspaces.find((item) => item.id === saved) || workspaces[0] || null;
        if (workspace && workspace.id !== saved) localStorage.setItem("forge_org_id", workspace.id);
        const githubResponse = await fetch("/api/v1/repositories/github-repos", { signal: controller.signal }).catch(() => null);
        const github = githubResponse?.ok ? "connected" : githubResponse && [400, 401, 403].includes(githubResponse.status) ? "missing" : "unknown";
        if (!workspace) { setData({ workspace, repositories: [], tasks: [], providerState: "unknown", github }); return; }
        const headers = { "X-Organization-Id": workspace.id };
        const [repoResult, planResult, providerResult] = await Promise.allSettled([
          request<{ repositories: Repository[] }>("/api/v1/repositories/imported", headers, controller.signal),
          request<{ plans: Plan[] }>("/api/v1/plans", headers, controller.signal),
          request<{ config: { provider?: string; api_key?: string } }>("/api/v1/auth/workspaces/current/provider", headers, controller.signal),
        ]);
        if (repoResult.status === "rejected" || planResult.status === "rejected") throw new Error("Workspace activity is unavailable. Refresh to try again.");
        const plans = (planResult.value.plans || []).slice(0, 8);
        const tasks = await Promise.all(plans.map(async (plan): Promise<Task> => {
          const task: Task = { ...plan };
          const job = await request<Job>(`/api/v1/executions/plans/${plan.id}/latest`, headers, controller.signal).catch((cause: unknown) => {
            if (!(cause instanceof Error && cause.message === "404")) task.jobUnavailable = true;
            return null;
          });
          if (!job) return task;
          task.job = job;
          if (job.status === "COMPLETED") {
            const [verification, patch] = await Promise.all([
              request<{ status: string }>(`/api/v1/verifications/executions/${job.id}/latest`, headers, controller.signal).catch((cause: unknown) => {
                if (!(cause instanceof Error && cause.message === "404")) task.verificationUnavailable = true;
                return null;
              }),
              request<Patch>(`/api/v1/patches/executions/${job.id}`, headers, controller.signal).catch(() => null),
            ]);
            if (verification) task.verification = verification.status;
            if (patch) task.patch = patch;
          }
          return task;
        }));
        if (controller.signal.aborted) return;
        const config = providerResult.status === "fulfilled" ? providerResult.value.config : null;
        const providerState = providerResult.status === "rejected" ? "unknown" : config?.provider && config.api_key ? "configured" : "missing";
        setData({ workspace, repositories: repoResult.value.repositories || [], tasks, providerState, github });
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error && !/^\d+$/.test(cause.message) ? cause.message : "Workspace activity is unavailable. Refresh to try again.");
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  const attention = data?.tasks.filter((task) => attentionStates.has(stateOf(task))) || [];
  const next = !data?.workspace ? { label: "Choose a workspace", href: "/settings/workspaces", detail: "Create a boundary for repositories, plans, and credentials." }
    : data.github === "missing" ? { label: "Connect GitHub", href: "/login", detail: "Authorize repository discovery before importing code." }
    : data.github === "unknown" && data.repositories.length === 0 ? { label: "Check GitHub access", href: "/repositories", detail: "Connection status could not be confirmed. Check discovery before importing." }
    : data.repositories.length === 0 ? { label: "Import a repository", href: "/repositories", detail: "Give Forge a real codebase to work with." }
    : data.providerState === "missing" ? { label: "Configure a model", href: "/settings/provider", detail: "Add a provider key before creating a plan." }
    : data.tasks.length === 0 ? { label: "Create your first task", href: `/repositories/${data.repositories[0].id}`, detail: "Describe a change and review the plan before execution." } : null;
  const setup = data ? [
    { label: "GitHub", state: data.github === "connected" ? "Connected" : data.github === "missing" ? "Needs connection" : "Unknown" },
    { label: "Workspace", state: data.workspace ? "Selected" : "Needed" },
    { label: "Repository", state: data.repositories.length ? "Imported" : "Needed" },
    { label: "Model", state: data.providerState === "configured" ? "Configured" : data.providerState === "missing" ? "Needed" : "Unknown" },
    { label: "First task", state: data.tasks.length ? "Created" : "Next" },
  ] : [];

  return <AppShell><div className="product-dashboard page-frame">
    <header className="product-heading"><div><p>Forge / {data?.workspace?.name || "Workspace"}</p><h1>Move the work forward.</h1><span>Plan in context. Approve deliberately. Verify every change.</span></div><Link className="button button-primary" href="/repositories">Open repositories →</Link></header>
    {error && <div className="product-alert" role="alert"><strong>Workspace activity could not load.</strong><p>{error}</p><button type="button" onClick={() => window.location.reload()}>Retry</button></div>}
    {!data && !error && <div className="data-state"><span className="loading-orbit" aria-hidden="true" />Reading workspace activity</div>}
    {data && <>
      {next && <section className="product-next" aria-labelledby="next-title"><div><span>Next useful step</span><h2 id="next-title">{next.label}</h2><p>{next.detail}</p></div><Link className="button button-white" href={next.href}>Continue →</Link></section>}
      {next && <ol className="product-setup" aria-label="Setup progress">{setup.map((step, index) => <li key={step.label}><span>{String(index + 1).padStart(2, "0")} · {step.label}</span><strong>{step.state}</strong></li>)}</ol>}
      {data.github === "unknown" && <p className="product-small-note">GitHub connection status is unavailable. Check repository discovery before importing.</p>}
      {data.providerState === "unknown" && data.workspace && <p className="product-small-note">Model configuration status is unavailable. Check provider settings before planning.</p>}
      <div className="product-columns">
        <section className="product-section" aria-labelledby="attention-title"><div className="product-section-head"><h2 id="attention-title">Needs a decision</h2><span>{attention.length}</span></div>{attention.length ? <ul className="product-list">{attention.map((task) => <li key={task.id}><Link href={`/tasks/${task.id}`}><strong>{task.intent}</strong><span>{stateOf(task)} ↗</span></Link></li>)}</ul> : <div className="product-empty"><p>No task currently needs your decision.</p><Link href="/tasks">Browse task history →</Link></div>}</section>
        <section className="product-section" aria-labelledby="recent-title"><div className="product-section-head"><h2 id="recent-title">Recent tasks</h2><Link href="/tasks">All tasks →</Link></div>{data.tasks.length ? <ul className="product-list">{data.tasks.slice(0, 5).map((task) => <li key={task.id}><Link href={`/tasks/${task.id}`}><strong>{task.intent}</strong><span>{stateOf(task)} · <time dateTime={task.created_at}>{new Date(task.created_at).toLocaleDateString()}</time></span></Link></li>)}</ul> : <div className="product-empty"><p>Plans and outcomes will appear after your first task.</p><Link href={data.repositories[0] ? `/repositories/${data.repositories[0].id}` : "/repositories"}>Start from a repository →</Link></div>}</section>
      </div>
      <section className="product-section product-repositories" aria-labelledby="repo-title"><div className="product-section-head"><h2 id="repo-title">Repository context</h2><Link href="/repositories">Discover repositories →</Link></div>{data.repositories.length ? <ul className="product-repo-list">{data.repositories.slice(0, 4).map((repo) => <li key={repo.id}><Link href={`/repositories/${repo.id}`}><strong>{repo.owner}/{repo.name}</strong><span>{repo.default_branch || "Branch unavailable"} · {repo.status.replaceAll("_", " ").toLowerCase()}{repo.indexing_status ? ` · index ${repo.indexing_status.replaceAll("_", " ").toLowerCase()}` : ""}</span><b aria-hidden="true">↗</b></Link></li>)}</ul> : <div className="product-empty"><p>No repository has been imported into this workspace.</p><Link href="/repositories">Choose a GitHub repository →</Link></div>}</section>
    </>}
  </div></AppShell>;
}
