"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { env } from "../../../config/env";
import { AppShell } from "../../components/AppShell";

export default function ProviderSettingsPage() {
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  useEffect(() => {
    fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/workspaces/current/provider`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("forge_token")}`, "X-Organization-Id": localStorage.getItem("forge_org_id") || "" },
    }).then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      if (data.config?.provider) { setProvider(data.config.provider); setApiKey(data.config.api_key || ""); setModel(data.config.model || "gpt-4o"); }
    }).catch(console.error).finally(() => setLoading(false));
  }, []);
  const save = async () => {
    setSaving(true); setSuccess(false);
    try {
      const response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/workspaces/current/provider`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${localStorage.getItem("forge_token")}`, "X-Organization-Id": localStorage.getItem("forge_org_id") || "", "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, model }),
      });
      if (!response.ok) throw new Error("Save failed");
      setSuccess(true); window.setTimeout(() => setSuccess(false), 3000);
    } catch (error) { console.error(error); window.alert("The provider configuration could not be saved."); }
    finally { setSaving(false); }
  };
  if (loading) return <AppShell><div className="data-state full-page-state"><span className="loading-orbit" />Reading provider configuration</div></AppShell>;
  return (
    <AppShell><div className="page-frame">
      <header className="page-intro settings-intro"><div className="section-label"><span>04</span>System configuration</div><h1>Choose the<br />planning engine.</h1><p>Provider credentials are stored against the active workspace and used during planning and code execution.</p></header>
      <nav className="settings-switcher"><Link href="/settings/provider" className="is-active"><span>01</span>Provider</Link><Link href="/settings/workspaces"><span>02</span>Workspaces</Link></nav>
      <section className="settings-field">
        <div className="settings-field-copy"><span>Provider boundary</span><h2>One explicit model configuration per workspace.</h2><p>Forge sends planning requests to the provider selected here. Execution remains inside the repository sandbox.</p><code>Settings / Provider / Active workspace</code></div>
        <form className="settings-form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <label><span className="field-label">Provider</span><select className="forge-select" value={provider} onChange={(e) => setProvider(e.target.value)}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="google">Google Gemini</option></select></label>
          <label><span className="field-label">API key</span><input className="forge-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter provider API key"} autoComplete="off" /><small>Keys are encrypted at rest and not exposed to the sandbox execution environment.</small></label>
          <label><span className="field-label">Default model</span><input className="forge-input mono-input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o" /></label>
          <div className="form-action"><span className={`save-success ${success ? "is-visible" : ""}`}>Configuration saved.</span><button className="button button-primary" type="submit" disabled={saving || !apiKey}>{saving ? "Saving…" : "Save configuration"} <span>→</span></button></div>
        </form>
      </section>
    </div></AppShell>
  );
}
