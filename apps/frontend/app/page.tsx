"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { env } from "../config/env";
import { AppShell } from "./components/AppShell";

type Repository = { id: string; name: string; owner: string; status: string; default_branch: string };

export default function DashboardPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);
    fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/repositories/imported`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("forge_token")}`,
        "X-Organization-Id": localStorage.getItem("forge_org_id") || "",
      },
      signal: controller.signal,
    })
      .then(async (response) => {
        window.clearTimeout(timeoutId);
        if (response.ok) {
          const data = await response.json();
          setRepos(data.repositories || []);
        }
      })
      .catch((error) => console.error("Failed to fetch repositories:", error))
      .finally(() => setLoading(false));
    return () => { window.clearTimeout(timeoutId); controller.abort(); };
  }, []);

  return (
    <AppShell>
      <section className="hero workspace-hero" aria-labelledby="workspace-title">
        <div className="hero-copy">
          <p className="eyebrow"><span aria-hidden="true" />Your engineering workspace</p>
          <h1 id="workspace-title"><span>From intent</span><span>to verified</span><span>change.</span></h1>
          <p className="hero-description">Import a repository, describe the change, inspect the plan, and keep execution evidence in one deliberate path.</p>
          <div className="hero-actions">
            <button className="button button-primary" type="button" onClick={() => router.push("/repositories")}>Import repository <span aria-hidden="true">→</span></button>
            <Link className="button button-secondary" href="/tasks">Review runs <span aria-hidden="true">↗</span></Link>
          </div>
        </div>
        <div className="hero-proof" aria-label="Forge execution lifecycle">
          {["Repository", "Context", "Plan", "Execute", "Verify"].map((stage, index) => (
            <span key={stage}><i>{String(index + 1).padStart(2, "0")}</i>{stage}</span>
          ))}
        </div>
      </section>

      <section className="dashboard-field" aria-labelledby="repositories-title">
        <div className="dashboard-field-heading reveal">
          <div className="section-label section-label-light"><span>01</span>Workspace</div>
          <h2 id="repositories-title">Repository context,<br />ready when you are.</h2>
          <div className="workspace-summary">
            <span><i>Imported</i><strong>{loading ? "—" : String(repos.length).padStart(2, "0")}</strong></span>
            <span><i>Active runs</i><strong>00</strong></span>
          </div>
        </div>
        <div className="repository-ledger reveal">
          <div className="ledger-head"><span>Repository</span><span>Branch</span><span>Status</span><span>Open</span></div>
          {loading ? (
            <div className="ledger-state"><span className="loading-orbit" />Reading workspace</div>
          ) : repos.length === 0 ? (
            <div className="ledger-empty">
              <div><span>00 / No repository context</span><h3>Start with a codebase.</h3><p>Connect a GitHub repository to let Forge map its structure before planning a change.</p></div>
              <Link className="button button-white" href="/repositories">Browse GitHub <span>→</span></Link>
            </div>
          ) : repos.slice(0, 5).map((repo, index) => (
            <Link className="ledger-row" href={`/repositories/${repo.id}`} key={repo.id}>
              <span className="ledger-repo"><i>{String(index + 1).padStart(2, "0")}</i><strong>{repo.name}</strong><small>{repo.owner}/{repo.name}</small></span>
              <code>{repo.default_branch || "main"}</code>
              <span className={`status-dot status-${repo.status?.toLowerCase()}`}>{repo.status || "Pending"}</span>
              <b>↗</b>
            </Link>
          ))}
        </div>
        <div className="dashboard-field-footer reveal">
          <p>Forge keeps context, planning, execution, and verification inspectable—not hidden behind a chat response.</p>
          <Link href="/repositories">All repositories <span>→</span></Link>
        </div>
      </section>
    </AppShell>
  );
}
