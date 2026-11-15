"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../components/AppShell";
const CustomSelect = ({ value, onChange, options }: { value: string, onChange: (val: string) => void, options: {label: string, value: string}[] }) => {
  return <select className="forge-select" value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>;
}

export default function ProviderSettingsPage() {
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [testMessage, setTestMessage] = useState("");
  const [testing, setTesting] = useState(false);
  const [loadError, setLoadError] = useState("");
  
  useEffect(() => {
    fetch(`/api/v1/auth/workspaces/current/provider`, {
      headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "" },
    }).then(async (response) => {
      if (!response.ok) { setLoadError("Provider configuration could not be loaded. Refresh before changing it."); return; }
      const data = await response.json();
      if (data.config?.provider) { setProvider(data.config.provider); setApiKey(data.config.api_key || ""); setModel(data.config.model || "gpt-4o"); }
    }).catch(() => setLoadError("Provider configuration could not be loaded. Refresh before changing it.")).finally(() => setLoading(false));
  }, []);

  const testConnection = async () => {
    setTesting(true); setTestMessage("");
    try {
      const response = await fetch(`/api/v1/auth/workspaces/current/provider/test`, {
        method: "POST", headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "", "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey }),
      });
      const result = await response.json().catch(() => ({}));
      setTestMessage(response.ok ? "Connection confirmed by the provider." : typeof result.detail === "string" ? result.detail : "The connection test failed. Check the key and provider.");
    } catch { setTestMessage("The connection test could not reach Forge. Try again."); }
    finally { setTesting(false); }
  };
  
  const save = async () => {
    setSaving(true); setSuccess(false); setTestMessage("");
    try {
      const response = await fetch(`/api/v1/auth/workspaces/current/provider`, {
        method: "PUT",
        headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "", "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: apiKey, model }),
      });
      if (!response.ok) throw new Error("Save failed");
      setSuccess(true); window.setTimeout(() => setSuccess(false), 3000);
    } catch (error) { console.error(error); window.alert("The provider configuration could not be saved."); }
    finally { setSaving(false); }
  };
  
  if (loading) return <AppShell><div className="data-state full-page-state"><span className="loading-orbit" />Reading provider configuration</div></AppShell>;
  
  const providerOptions = [
    { label: "OpenAI", value: "openai" },
    { label: "Anthropic", value: "anthropic" },
    { label: "Google Gemini", value: "google" },
    { label: "Groq", value: "groq" }
  ];

  const modelOptions: Record<string, {label: string, value: string}[]> = {
    openai: [
      { label: "GPT-4o", value: "gpt-4o" },
      { label: "GPT-4 Turbo", value: "gpt-4-turbo" },
      { label: "GPT-3.5 Turbo", value: "gpt-3.5-turbo" },
    ],
    anthropic: [
      { label: "Claude 3.5 Sonnet", value: "claude-3-5-sonnet-20240620" },
      { label: "Claude 3 Opus", value: "claude-3-opus-20240229" },
      { label: "Claude 3 Haiku", value: "claude-3-haiku-20240307" },
    ],
    google: [
      { label: "Gemini 1.5 Pro", value: "gemini-1.5-pro-latest" },
      { label: "Gemini 1.5 Flash", value: "gemini-1.5-flash-latest" },
    ],
    groq: [
      { value: "groq/llama-3.1-8b-instant", label: "LLaMA 3.1 8B (groq/llama-3.1-8b-instant)" },
      { value: "groq/llama-3.3-70b-versatile", label: "LLaMA 3.3 70B (groq/llama-3.3-70b-versatile)" },
      { value: "groq/mixtral-8x7b-32768", label: "Mixtral 8x7B (groq/mixtral-8x7b-32768)" },
      { value: "groq/gemma2-9b-it", label: "Gemma 2 9B (groq/gemma2-9b-it)" },
    ]
  };

  return (
    <AppShell><div className="page-frame">
      <header className="page-intro settings-intro"><div className="section-label"><span>04</span>System configuration</div><h1>Choose the<br />planning engine.</h1><p>Provider credentials are stored against the active workspace and used during planning and code execution.</p></header>
      <nav className="settings-switcher"><Link href="/settings/provider" className="is-active"><span>01</span>Provider</Link><Link href="/settings/workspaces"><span>02</span>Workspaces</Link><Link href="/settings/safety"><span>03</span>Safety Gate</Link></nav>
      <section className="settings-field">
        <div className="settings-field-copy"><span>Provider boundary</span><h2>One explicit model configuration per workspace.</h2><p>Forge sends planning requests to the provider selected here. Execution remains inside the repository sandbox.</p><code>Settings / Provider / Active workspace</code></div>
        <form className="settings-form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <label>
            <span className="field-label">Provider</span>
            <CustomSelect value={provider} onChange={(val) => {
              setProvider(val); setApiKey(""); setTestMessage("");
              if (val === "groq") setModel("groq/llama-3.1-8b-instant");
              else if (val === "openai") setModel("gpt-4o");
              else if (val === "anthropic") setModel("claude-3-5-sonnet-20240620");
              else if (val === "google") setModel("gemini-1.5-pro-latest");
            }} options={providerOptions} />
          </label>
          <label><span className="field-label">API key</span><input className="forge-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter provider API key"} autoComplete="off" /><small>Keys are encrypted at rest and not exposed to the sandbox execution environment.</small></label>
          <label>
            <span className="field-label">Default model</span>
            <CustomSelect value={model} onChange={setModel} options={modelOptions[provider] || modelOptions.openai} />
          </label>
          {loadError && <p className="form-message form-error" role="alert">{loadError}</p>}
          <p className="provider-state" aria-live="polite">{apiKey ? "A key is present for this selection. Save changes before relying on a new configuration." : "No key entered for this provider."}</p>
          {testMessage && <p className="provider-state" role="status">{testMessage}</p>}
          {provider === "google" && <p className="provider-state">Forge can save a Google model configuration, but the API does not currently offer a Google connection test.</p>}
          <div className="form-action"><span className={`save-success ${success ? "is-visible" : ""}`}>Configuration saved.</span><div className="provider-actions"><button className="button button-secondary" type="button" disabled={testing || !apiKey || provider === "google" || Boolean(loadError)} onClick={() => void testConnection()}>{testing ? "Testing…" : "Test connection"}</button><button className="button button-primary" type="submit" disabled={saving || !apiKey || Boolean(loadError)}>{saving ? "Saving…" : "Save configuration"} <span>→</span></button></div></div>
        </form>
      </section>
    </div></AppShell>
  );
}
