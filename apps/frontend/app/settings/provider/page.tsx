'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Key, Save, Loader2, Cpu } from "lucide-react";

export default function ProviderSettingsPage() {
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const fetchConfig = async () => {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      
      try {
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/workspaces/current/provider`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Organization-Id": orgId || ""
          }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.config && data.config.provider) {
            setProvider(data.config.provider);
            setApiKey(data.config.api_key || "");
            setModel(data.config.model || "gpt-4o");
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchConfig();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSuccess(false);
    try {
      const token = localStorage.getItem("forge_token");
      const orgId = localStorage.getItem("forge_org_id");
      
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/workspaces/current/provider`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "X-Organization-Id": orgId || "",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          model
        })
      });
      
      if (res.ok) {
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-8 animate-pulse text-muted">Loading settings...</div>;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">AI Provider Configuration</h1>
        <p className="text-muted">Configure the LLM provider for Forge AI to use during planning and execution.</p>
      </div>

      <div className="bg-surface border border-border rounded-xl p-8 space-y-6">
        <div>
          <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-accent" /> Provider
          </label>
          <select 
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-full bg-black border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="google">Google Gemini</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
            <Key className="w-4 h-4 text-accent" /> API Key
          </label>
          <input 
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter your API key"}
            className="w-full bg-black border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent font-mono"
          />
          <p className="text-xs text-muted mt-2">Keys are encrypted at rest and never exposed to the execution sandbox.</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-2">Default Model</label>
          <input 
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. gpt-4o, claude-3-5-sonnet"
            className="w-full bg-black border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent font-mono text-sm"
          />
        </div>
        
        <div className="pt-4 border-t border-border flex items-center justify-between">
          <div>
            {success && <span className="text-green-400 text-sm font-medium">Settings saved successfully.</span>}
          </div>
          <button 
            onClick={handleSave}
            disabled={saving || !apiKey}
            className="bg-accent hover:bg-accent/90 text-white px-6 py-2.5 rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Configuration
          </button>
        </div>
      </div>
    </div>
  );
}
