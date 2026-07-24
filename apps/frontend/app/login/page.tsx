'use client';

import React from "react";
import { env } from "../../config/env";
import { Github } from "lucide-react";
import { Button } from "../components/ui/button";

export default function LoginPage() {
  const handleGithubLogin = async () => {
    try {
      const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/github/login`);
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err) {
      console.error("Failed to fetch login url", err);
    }
  };

  return (
    <div className="flex h-screen w-full items-center justify-center bg-slate-50 overflow-hidden relative">
      {/* Background decorations matching the Forge aesthetic */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-blue-100 rounded-full blur-3xl opacity-50 pointer-events-none"></div>
      
      <div className="relative z-10 flex flex-col items-center gap-8 p-12 bg-white/70 backdrop-blur-xl border border-slate-200/60 rounded-3xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.05)] max-w-md w-full text-center">
        <div className="w-20 h-20 bg-gradient-to-tr from-blue-600 to-blue-400 flex items-center justify-center rounded-2xl shadow-lg shadow-blue-500/20 mb-2">
          <span className="text-4xl text-white font-bold leading-none tracking-tighter brand-mark relative top-0">F</span>
        </div>
        
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 mb-3">Welcome to Forge</h1>
          <p className="text-slate-500 font-medium">Autonomous Software Engineering Platform</p>
        </div>
        
        <div className="w-full pt-4">
          <Button
            onClick={handleGithubLogin}
            className="w-full !min-h-14 !text-base bg-[#18181b] hover:bg-[#27272a] shadow-xl shadow-slate-900/10 border border-slate-800"
          >
            <Github className="w-5 h-5 mr-2" />
            Continue with GitHub
          </Button>
        </div>
        
        <p className="text-xs text-slate-400 font-medium mt-4">
          By signing in, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
}
