"use client";

import { useState } from "react";
import { env } from "../../config/env";

export default function LoginPage() {
  const [connecting, setConnecting] = useState(false);
  const connect = async () => {
    setConnecting(true);
    try {
      const response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/auth/github/login`);
      const data = await response.json();
      if (!data.url) throw new Error("Missing authorization URL");
      try {
        window.location.href = data.url;
      } catch (e) {
        window.open(data.url, "_blank");
      }
      // Fallback if location.href is silently blocked
      setTimeout(() => {
        window.open(data.url, "_blank");
      }, 500);
    } catch (error) {
      console.error(error); window.alert("Forge could not begin GitHub authentication."); setConnecting(false);
    }
  };
  return (
    <main className="login-shell">
      <header className="site-header login-header"><div className="brand"><span className="brand-mark">F</span><strong>Forge</strong></div><span>GitHub-connected engineering workspace</span></header>
      <section className="hero login-hero" aria-labelledby="login-title">
        <div className="hero-copy">
          <p className="eyebrow"><span />Intent to verified change</p>
          <h1 id="login-title"><span>Enter the</span><span>Forge.</span></h1>
          <p className="hero-description">Connect GitHub to import repositories, inspect plans, and keep execution evidence attached to every change.</p>
          <div className="hero-actions"><button type="button" className="button button-primary login-action" onClick={connect} disabled={connecting}>{connecting ? "Connecting…" : "Continue with GitHub"} <span>↗</span></button></div>
        </div>
        <div className="hero-proof">{["Import", "Understand", "Plan", "Execute", "Verify"].map((stage, index) => <span key={stage}><i>{String(index + 1).padStart(2, "0")}</i>{stage}</span>)}</div>
      </section>
    </main>
  );
}
