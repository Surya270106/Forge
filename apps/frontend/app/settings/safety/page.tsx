"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../components/AppShell";
import "../../bench/bench.css";

type Policy = { version: number; denied: string[]; repository_denies: Record<string, string[]>; stopped: boolean };
type Revision = Policy & { created_at: string; created_by: string };
const capabilities = [
  { id: "repository:write", label: "Edit repository files" },
  { id: "command:execute", label: "Run checked commands in Docker" },
  { id: "patch:publish", label: "Publish an approved patch" },
];
const headers = () => ({ "X-Organization-Id": localStorage.getItem("forge_org_id") || "" });

export default function SafetySettingsPage() {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [history, setHistory] = useState<Revision[]>([]);
  const [denied, setDenied] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [policyResponse, historyResponse] = await Promise.all([
      fetch("/api/v1/safety/policy", { headers: headers(), signal }),
      fetch("/api/v1/safety/history", { headers: headers(), signal }),
    ]);
    if (!policyResponse.ok || !historyResponse.ok) throw new Error(policyResponse.status === 403 ?
      "Only workspace administrators can manage Safety Gate." : "Safety Gate could not be loaded.");
    const [nextPolicy, nextHistory] = await Promise.all([policyResponse.json(), historyResponse.json()]);
    setPolicy(nextPolicy); setDenied(nextPolicy.denied); setHistory(nextHistory.revisions || []);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal).catch((cause) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Safety Gate is unavailable.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refresh]);

  const change = async (path: string, method: "POST" | "PUT", body?: object) => {
    setSaving(true); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/v1/safety/${path}`, {
        method, headers: { ...headers(), "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) throw new Error("Safety policy was not changed. Refresh and try again.");
      await refresh();
      setNotice("Policy saved. Active workers will recheck restrictions before their next action.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Safety Gate is unavailable."); }
    finally { setSaving(false); }
  };

  return <AppShell><div className="page-frame">
    <header className="page-intro settings-intro"><div className="section-label"><span>05</span>Safety Gate</div><h1>Set the execution<br />boundary.</h1><p>Workspace restrictions are checked by the worker before each agent action. Changes cannot grant a running execution more access than its original snapshot.</p></header>
    <nav className="settings-switcher"><Link href="/settings/provider"><span>01</span>Provider</Link><Link href="/settings/workspaces"><span>02</span>Workspaces</Link><Link href="/settings/safety" className="is-active"><span>03</span>Safety Gate</Link></nav>
    {error && <p className="product-alert" role="alert">{error}</p>}
    {notice && <p className="bench-notice" role="status">{notice}</p>}
    {loading ? <div className="data-state"><span className="loading-orbit" />Loading safety policy</div> : policy && <>
      <section className="settings-field">
        <div className="settings-field-copy"><span>Policy v{policy.version}</span><h2>{policy.stopped ? "Emergency stop active." : "Capabilities are scoped."}</h2><p>Protected paths, shell operators, unknown tools, and unenforced sandbox network access are blocked by platform rules. Patch publication still requires exact digest human review.</p><code>Workspace / Safety Gate / v{policy.version}</code></div>
        <div className="settings-form">
          <h3>Organization restrictions</h3><p>Check a capability to deny it for new and active executions.</p>
          {capabilities.map((capability) => <label key={capability.id} className="bench-task"><input type="checkbox" checked={denied.includes(capability.id)} onChange={() => setDenied((current) => current.includes(capability.id) ? current.filter((item) => item !== capability.id) : [...current, capability.id])} /><span><strong>{capability.label}</strong><small>{capability.id}</small></span></label>)}
          <button type="button" className="button" disabled={saving} onClick={() => void change("policy", "PUT", { denied, repository_denies: policy.repository_denies })}>Save restrictions</button>
          <div className="form-action"><button type="button" className="button" disabled={saving || policy.stopped} onClick={() => { if (window.confirm("Stop new and active Forge executions in this workspace?")) void change("emergency-stop", "POST"); }}>Emergency stop</button><button type="button" className="button" disabled={saving || !policy.stopped} onClick={() => { if (window.confirm("Resume new Forge executions in this workspace?")) void change("resume", "POST"); }}>Resume after review</button></div>
        </div>
      </section>
      <section className="bench-history"><div className="bench-section-heading"><div><span className="section-label">Policy history</span><h2>Recorded revisions</h2></div></div>{history.length ? history.map((revision) => <div className="bench-history-row" key={revision.version}><strong>v{revision.version}</strong><span>{revision.stopped ? "STOPPED" : revision.denied.length ? `${revision.denied.length} restrictions` : "Default capabilities"}</span><time>{new Date(revision.created_at).toLocaleString()}</time></div>) : <div className="data-state">No restrictions have been recorded.</div>}</section>
    </>}
  </div></AppShell>;
}
