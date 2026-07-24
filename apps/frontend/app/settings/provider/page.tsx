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
      <div className="flex flex-col items-center justify-center py-24 text-slate-500 gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" /> 
        <span className="font-medium">Loading settings...</span>
      </div>
    </AppShell>
  );

  return (
    <AppShell>
      <div className="mb-8 max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 mb-2">AI Provider Configuration</h1>
        <p className="text-slate-500">Configure the language model provider Forge AI will use during planning and code execution.</p>
      </div>

      <Card className="max-w-2xl">
        <CardContent className="p-8 space-y-8">
          <div>
            <label className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-slate-400" /> Provider
            </label>
            <select 
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 transition-all font-medium appearance-none"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google Gemini</option>
            </select>
          </div>

          <div>
            <label className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Key className="w-4 h-4 text-slate-400" /> API Key
            </label>
            <input 
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={apiKey.startsWith("sk-") ? "••••••••••••••••••••••••" : "Enter your API key"}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 transition-all font-mono shadow-sm"
            />
            <p className="text-xs text-slate-500 mt-2 font-medium">Keys are encrypted at rest and never exposed to the sandbox execution environment.</p>
          </div>

          <div>
            <label className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">Default Model</label>
            <input 
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o, claude-3-5-sonnet"
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 transition-all font-mono text-sm shadow-sm"
            />
          </div>
          
          <div className="pt-8 border-t border-slate-100 flex items-center justify-between">
            <div className="h-6">
              {success && (
                <span className="text-green-600 text-sm font-medium flex items-center gap-2 animate-in fade-in duration-300">
                  <CheckCircle className="w-4 h-4" /> Settings saved successfully
                </span>
              )}
            </div>
            <Button 
              onClick={handleSave}
              disabled={saving || !apiKey}
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
              Save Configuration
            </Button>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
