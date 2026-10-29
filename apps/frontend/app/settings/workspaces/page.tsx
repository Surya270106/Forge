"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../components/AppShell";

type Workspace = { id: string; name: string; role: string };

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const fetchWorkspaces = async () => {
    try {
      const response = await fetch(`/api/v1/auth/workspaces`);
      if (response.ok) { const data = await response.json(); setWorkspaces(data.workspaces || []); }
    } catch (error) { console.error(error); } finally { setLoading(false); }
  };
  useEffect(() => { void fetchWorkspaces(); }, []);
  const create = async () => {
    if (!name.trim()) return; setCreating(true);
    try {
      const response = await fetch(`/api/v1/workspaces`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
      if (!response.ok) throw new Error("Create failed");
      setName(""); await fetchWorkspaces();
    } catch (error) { console.error(error); window.alert("The workspace could not be created."); } finally { setCreating(false); }
  };
  const switchWorkspace = (id: string) => { localStorage.setItem("forge_org_id", id); window.location.reload(); };
  if (loading) return <AppShell><div className="data-state full-page-state"><span className="loading-orbit" />Reading workspaces</div></AppShell>;
  const current = typeof window === "undefined" ? "" : localStorage.getItem("forge_org_id");
  return (
    <AppShell><div className="page-frame">
      <header className="page-intro settings-intro"><div className="section-label"><span>04</span>System configuration</div><h1>Keep every team<br />boundary explicit.</h1><p>Workspaces scope repository context, plans, execution evidence, credentials, and audit history.</p></header>
      <nav className="settings-switcher"><Link href="/settings/provider"><span>01</span>Provider</Link><Link href="/settings/workspaces" className="is-active"><span>02</span>Workspaces</Link></nav>
      <section className="workspace-editor">
        <div className="workspace-create"><span>Create workspace</span><h2>A new boundary for code and execution.</h2><div><input className="forge-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Workspace name" /><button type="button" className="button button-primary" disabled={creating || !name.trim()} onClick={create}>{creating ? "Creating…" : "Create workspace"} <span>→</span></button></div></div>
        <div className="workspace-list">
          <div className="data-ledger-head workspace-ledger-grid"><span>Workspace</span><span>Role</span><span>Context</span></div>
          {workspaces.length === 0 ? <div className="data-state">No workspaces were returned.</div> : workspaces.map((workspace, index) => (
            <article className="workspace-ledger-grid" key={workspace.id}>
              <div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{workspace.name}</h2><p>{workspace.id.slice(0, 12).toUpperCase()}</p></div></div><code>{workspace.role}</code>
              {workspace.id === current ? <span className="status-ink status-completed">Current</span> : <button className="row-action" type="button" onClick={() => switchWorkspace(workspace.id)}>Switch <span>→</span></button>}
            </article>
          ))}
        </div>
      </section>
    </div></AppShell>
  );
}
