'use client';

import React from "react";
import { env } from "../../config/env";
import { Github } from "lucide-react";

export default function LoginPage() {
  const handleGithubLogin = async () => {
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/auth/github/login`);
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err) {
      console.error("Failed to fetch login url", err);
    }
  };

  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-6 p-10 bg-surface border border-border rounded-xl shadow-lg max-w-sm w-full text-center">
        <div className="w-16 h-16 bg-accent/10 flex items-center justify-center rounded-xl border border-accent/20">
          <span className="text-3xl">⚒️</span>
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-2">Welcome to Forge</h1>
          <p className="text-muted text-sm">Autonomous Software Engineering Platform</p>
        </div>
        <button
          onClick={handleGithubLogin}
          className="w-full flex items-center justify-center gap-3 bg-[#24292e] hover:bg-[#2f363d] text-white px-4 py-3 rounded-lg font-medium transition-colors"
        >
          <Github className="w-5 h-5" />
          Continue with GitHub
        </button>
      </div>
    </div>
  );
}
