'use client';

import React, { useEffect, useState } from "react";
import { env } from "../../../config/env";
import { Building2, Plus, Users, Settings as SettingsIcon } from "lucide-react";

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchWorkspaces = async () => {
    try {
      const token = localStorage.getItem("forge_token");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/workspaces`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setWorkspaces(data.workspaces);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  const handleCreate = async () => {
    if (!newWorkspaceName) return;
    setIsCreating(true);
    try {
      const token = localStorage.getItem("forge_token");
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/workspaces`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ name: newWorkspaceName })
      });
      if (res.ok) {
        setNewWorkspaceName("");
        await fetchWorkspaces();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const switchWorkspace = (id: string) => {
    localStorage.setItem("forge_org_id", id);
    window.location.reload(); // Quick way to force context refresh for MVP
  };

  if (loading) return <div className="p-8 animate-pulse text-muted">Loading workspaces...</div>;

  const currentOrgId = localStorage.getItem("forge_org_id");

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Workspaces</h1>
          <p className="text-muted">Manage your organizations and team access.</p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 mb-8">
        <h2 className="text-lg font-medium text-white mb-4">Create New Workspace</h2>
        <div className="flex gap-4">
          <input 
            type="text"
            value={newWorkspaceName}
            onChange={(e) => setNewWorkspaceName(e.target.value)}
            placeholder="Workspace Name"
            className="flex-1 bg-black border border-border rounded-md px-4 py-2 text-white focus:outline-none focus:border-accent"
          />
          <button 
            onClick={handleCreate}
            disabled={isCreating || !newWorkspaceName}
            className="bg-accent hover:bg-accent/90 text-white px-4 py-2 rounded-md font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <Plus className="w-4 h-4" /> Create
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {workspaces.map(ws => (
          <div key={ws.id} className={`bg-surface border ${ws.id === currentOrgId ? 'border-accent' : 'border-border'} rounded-xl p-6 relative`}>
            {ws.id === currentOrgId && (
              <div className="absolute top-4 right-4 text-xs font-semibold bg-accent/20 text-accent px-2 py-1 rounded-md">
                CURRENT
              </div>
            )}
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-accent/10 rounded-lg flex items-center justify-center text-accent">
                <Building2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-medium text-white">{ws.name}</h3>
                <p className="text-sm text-muted">Role: {ws.role}</p>
              </div>
            </div>
            
            <div className="flex items-center gap-2 mt-6">
              {ws.id !== currentOrgId && (
                <button 
                  onClick={() => switchWorkspace(ws.id)}
                  className="flex-1 bg-accent/10 hover:bg-accent/20 text-accent px-3 py-2 rounded-md text-sm font-medium transition-colors"
                >
                  Switch to Workspace
                </button>
              )}
              <button className="flex items-center gap-2 text-muted hover:text-white px-3 py-2 rounded-md text-sm font-medium transition-colors border border-border hover:border-gray-600">
                <SettingsIcon className="w-4 h-4" /> Settings
              </button>
              <button className="flex items-center gap-2 text-muted hover:text-white px-3 py-2 rounded-md text-sm font-medium transition-colors border border-border hover:border-gray-600">
                <Users className="w-4 h-4" /> Members
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
