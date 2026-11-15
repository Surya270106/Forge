"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../../components/AppShell";
import { motion, AnimatePresence } from "framer-motion";

const CustomSelect = ({ value, onChange, options }: { value: string, onChange: (val: string) => void, options: {label: string, value: string}[] }) => {
  const [open, setOpen] = useState(false);
  const selected = options.find(o => o.value === value) || options[0];

  return (
    <div className="custom-select-wrapper" style={{position: 'relative', width: '100%', outline: 'none'}} tabIndex={0} onBlur={(e) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false);
    }}>
      <div 
        className="forge-select" 
        style={{display: 'flex', alignItems: 'center', cursor: 'pointer', userSelect: 'none'}} 
        onClick={() => setOpen(!open)}
      >
        {selected.label}
        <span style={{marginLeft: 'auto', fontSize: '10px', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease'}}>▼</span>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div 
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="custom-select-dropdown" 
            style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100, 
              background: '#fff', border: '1px solid #9fbde3', borderRadius: '8px',
              boxShadow: '0 12px 24px rgba(0,0,0,0.1)', marginTop: '4px', overflow: 'hidden', padding: '4px'
            }}
          >
            {options.map(o => (
              <div 
                key={o.value} 
                style={{
                  padding: '12px 16px', cursor: 'pointer', borderRadius: '4px',
                  background: o.value === value ? 'rgb(240, 244, 255)' : 'transparent',
                  color: 'var(--ink, #000)',
                  fontWeight: o.value === value ? 600 : 500,
                  transition: 'background 0.15s ease'
                }}
                onClick={() => { onChange(o.value); setOpen(false); }}
                onMouseEnter={(e) => {
                  if (o.value !== value) e.currentTarget.style.background = 'rgb(248, 250, 255)';
                }}
                onMouseLeave={(e) => {
                  if (o.value !== value) e.currentTarget.style.background = 'transparent';
                }}
              >
                {o.label}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function ProviderSettingsPage() {
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  
  useEffect(() => {
    fetch(`/api/v1/auth/workspaces/current/provider`, {
      headers: { "X-Organization-Id": localStorage.getItem("forge_org_id") || "" },
    }).then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      if (data.config?.provider) { setProvider(data.config.provider); setApiKey(data.config.api_key || ""); setModel(data.config.model || "gpt-4o"); }
    }).catch(console.error).finally(() => setLoading(false));
  }, []);
  
  const save = async () => {
    setSaving(true); setSuccess(false);
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
      <nav className="settings-switcher"><Link href="/settings/provider" className="is-active"><span>01</span>Provider</Link><Link href="/settings/workspaces"><span>02</span>Workspaces</Link></nav>
      <section className="settings-field">
        <div className="settings-field-copy"><span>Provider boundary</span><h2>One explicit model configuration per workspace.</h2><p>Forge sends planning requests to the provider selected here. Execution remains inside the repository sandbox.</p><code>Settings / Provider / Active workspace</code></div>
        <form className="settings-form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <label>
            <span className="field-label">Provider</span>
            <CustomSelect value={provider} onChange={(val) => {
              setProvider(val);
              if (val === "groq") setModel("llama3-8b-8192");
              else if (val === "openai") setModel("gpt-4o");
              else if (val === "anthropic") setModel("claude-3-opus-20240229");
              else if (val === "google") setModel("gemini-1.5-pro-latest");
            }} options={providerOptions} />
          </label>
          <label><span className="field-label">API key</span><input className="forge-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter provider API key"} autoComplete="off" /><small>Keys are encrypted at rest and not exposed to the sandbox execution environment.</small></label>
          <label>
            <span className="field-label">Default model</span>
            <CustomSelect value={model} onChange={setModel} options={modelOptions[provider] || modelOptions.openai} />
          </label>
          <div className="form-action"><span className={`save-success ${success ? "is-visible" : ""}`}>Configuration saved.</span><button className="button button-primary" type="submit" disabled={saving || !apiKey}>{saving ? "Saving…" : "Save configuration"} <span>→</span></button></div>
        </form>
      </section>
    </div></AppShell>
  );
}
