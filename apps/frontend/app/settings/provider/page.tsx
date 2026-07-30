'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Key, Save, Loader2, Cpu, CheckCircle } from "lucide-react";
import { AppShell } from "../../components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";

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
        const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/workspaces/current/provider`, {
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
      
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/workspaces/current/provider`, {
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

  if (loading) return (
    <AppShell>
      <div className="flex flex-col items-center justify-center py-32 text-slate-500 gap-4">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
        <span className="font-medium text-sm">Loading settings...</span>
      </div>
    </AppShell>
  );

  return (
    <AppShell>
      <div className="mb-8 max-w-[640px]">
        <h1 className="text-[clamp(32px,3vw,44px)] font-semibold tracking-tight text-slate-900 mb-2 leading-tight">AI Provider Configuration</h1>
        <p className="text-slate-500">Configure the language model provider Forge AI will use during planning and code execution.</p>
      </div>

      <Card className="max-w-[640px] border-forge-line shadow-sm overflow-hidden bg-white/90 backdrop-blur-md">
        <CardContent className="p-0">
          <div className="p-6 md:p-8 space-y-7">
            <div>
              <label className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-slate-400" /> Provider
              </label>
              <select 
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full h-[42px] bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-medium appearance-none shadow-sm"
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="google">Google Gemini</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                <Key className="w-4 h-4 text-slate-400" /> API Key
              </label>
              <input 
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter your API key"}
                className="w-full h-[42px] bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-mono shadow-sm"
              />
              <p className="text-[11px] text-slate-500 mt-2.5 font-medium">Keys are encrypted at rest and never exposed to the sandbox execution environment.</p>
            </div>

            <div>
              <label className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">Default Model</label>
              <input 
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                className="w-full h-[42px] bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-mono shadow-sm"
              />
            </div>
          </div>
          
          <div className="p-6 md:p-8 pt-0 flex items-center justify-between">
            <div className="h-6 flex items-center min-w-0 pr-4">
              {success && (
                <span className="text-emerald-600 text-[13px] font-medium flex items-center gap-1.5 animate-in fade-in slide-in-from-bottom-1 duration-300">
                  <CheckCircle className="w-4 h-4" /> Configuration saved
                </span>
              )}
            </div>
            <Button 
              onClick={handleSave}
              disabled={saving || !apiKey}
              variant="primary"
              className="shrink-0"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {saving ? "Saving..." : "Save Configuration"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
