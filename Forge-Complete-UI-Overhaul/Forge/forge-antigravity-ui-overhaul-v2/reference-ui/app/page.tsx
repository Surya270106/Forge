"use client";

import { type KeyboardEvent, useEffect, useState } from "react";
import BlobScene from "./blob-scene";

const repositoryUrl = "https://github.com/Surya270106/Forge";

const lifecycle = [
  {
    title: "Read the repository",
    body: "Forge maps the codebase before proposing a change: files, languages, frameworks, dependencies, and the task-specific context that matters.",
    evidence: "Context Engine  /  Repository Manifest  /  PostgreSQL",
  },
  {
    title: "Plan the change",
    body: "The Planning Engine converts intent into an ordered graph of edits, commands, checks, and dependencies instead of improvising one opaque response.",
    evidence: "Planning Engine  /  Task DAG  /  Dependency Edges",
  },
  {
    title: "Execute in bounds",
    body: "Executable nodes run through a sandbox abstraction with workspace boundaries, timeouts, explicit capabilities, and captured mutations.",
    evidence: "Execution Engine  /  DockerSandbox  /  Mutation Model",
  },
  {
    title: "Prove the result",
    body: "Format, lint, type-check, test, build, and security checks decide whether a change advances or returns to a focused repair loop.",
    evidence: "Verification Registry  /  Diagnostics  /  Repair Loop",
  },
  {
    title: "Prepare the patch",
    body: "Passing mutations become a unified patch with a branch, commit, and pull-request lifecycle that stays ready for human review.",
    evidence: "Patch Engine  /  Git Client  /  Pull Request",
  },
];

const guardrails = [
  {
    number: "01",
    title: "Network isolation",
    body: "Execution can run without a bridge to the public network.",
  },
  {
    number: "02",
    title: "Reduced privileges",
    body: "Containers drop Linux capabilities and block privilege escalation.",
  },
  {
    number: "03",
    title: "Tenant boundaries",
    body: "PostgreSQL Row-Level Security scopes plans, runs, and audit data.",
  },
];

function Header() {
  return (
    <header className="site-header">
      <a className="brand" href="#top" aria-label="Forge AI home">
        <span className="brand-mark" aria-hidden="true">
          F
        </span>
        <strong>Forge</strong>
      </a>

      <nav className="main-nav" aria-label="Primary navigation">
        <a href="#platform">Platform</a>
        <a href="#workflow">Workflow</a>
        <a href="#security">Safety</a>
        <a href="#architecture">Architecture</a>
      </nav>

      <a
        className="header-source"
        href={repositoryUrl}
        target="_blank"
        rel="noreferrer"
      >
        View source <span aria-hidden="true">↗</span>
      </a>
    </header>
  );
}

export default function Home() {
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    let frame = 0;

    const updateBlobPresence = () => {
      const viewport = Math.max(window.innerHeight, 1);
      const heroExit = Math.min(Math.max(window.scrollY / (viewport * 0.88), 0), 1);

      document.documentElement.style.setProperty(
        "--blob-page-opacity",
        String(1 - heroExit * 0.78),
      );
      frame = 0;
    };

    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateBlobPresence);
    };

    updateBlobPresence();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.documentElement.style.removeProperty("--blob-page-opacity");
    };
  }, []);

  const handleStageKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    const lastIndex = lifecycle.length - 1;
    let nextIndex = index;

    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      nextIndex = index === lastIndex ? 0 : index + 1;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      nextIndex = index === 0 ? lastIndex : index - 1;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = lastIndex;
    } else {
      return;
    }

    event.preventDefault();
    setActiveStage(nextIndex);
    document.getElementById(`forge-stage-tab-${nextIndex}`)?.focus();
  };

  return (
    <main id="top">
      <BlobScene />
      <Header />

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">
            <span aria-hidden="true" />
            Open-source agentic software delivery
          </p>
          <h1 id="hero-title">
            <span>From intent</span>
            <span>to verified</span>
            <span>change.</span>
          </h1>
          <p className="hero-description">
            Forge understands a repository, plans the work, executes inside a
            boundary, and verifies the result before a patch reaches review.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#platform">
              Explore Forge <span aria-hidden="true">↓</span>
            </a>
            <a
              className="button button-secondary"
              href={repositoryUrl}
              target="_blank"
              rel="noreferrer"
            >
              GitHub repository <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
        <div className="hero-proof" aria-label="Forge execution lifecycle">
          {["Context", "Plan", "Execute", "Verify", "Review"].map(
            (stage, index) => (
              <span key={stage}>
                <i>{String(index + 1).padStart(2, "0")}</i>
                {stage}
              </span>
            ),
          )}
        </div>
      </section>

      <div className="forge-story">
        <section className="story-section platform-section" id="platform">
          <div className="section-label reveal">
            <span>01</span>
            Platform
          </div>
          <div className="platform-grid">
            <h2 className="reveal">
              Software change is a chain of evidence.
            </h2>
            <div className="platform-copy reveal">
              <p>
                A prompt is only the starting point. Forge keeps the path from
                request to patch inspectable, so every action has context,
                ownership, and a reason to advance.
              </p>
              <a href="#workflow">See the execution path <span>→</span></a>
            </div>
          </div>
          <div className="evidence-rail reveal" aria-label="Forge task lifecycle">
            {["Request", "Context", "Plan", "Execute", "Verify", "Patch"].map(
              (stage, index) => (
                <div key={stage}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{stage}</strong>
                </div>
              ),
            )}
          </div>
        </section>

        <section className="story-section workflow-section" id="workflow">
          <div className="workflow-heading reveal">
            <div className="section-label section-label-light">
              <span>02</span>
              Workflow
            </div>
            <h2>Every decision stays inspectable.</h2>
            <p>
              Select a stage to see what Forge is doing and which part of the
              system owns it.
            </p>
          </div>

          <div className="workflow-console reveal">
            <div
              className="lifecycle-list"
              role="tablist"
              aria-label="Forge lifecycle"
              aria-orientation="vertical"
            >
              {lifecycle.map((stage, index) => (
                <button
                  type="button"
                  role="tab"
                  id={`forge-stage-tab-${index}`}
                  aria-controls={`forge-stage-panel-${index}`}
                  aria-selected={activeStage === index}
                  tabIndex={activeStage === index ? 0 : -1}
                  className={activeStage === index ? "is-active" : ""}
                  onClick={() => setActiveStage(index)}
                  onKeyDown={(event) => handleStageKeyDown(event, index)}
                  key={stage.title}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{stage.title}</strong>
                  <i aria-hidden="true">→</i>
                </button>
              ))}
            </div>

            <div
              className="lifecycle-detail"
              role="tabpanel"
              id={`forge-stage-panel-${activeStage}`}
              aria-labelledby={`forge-stage-tab-${activeStage}`}
              aria-live="polite"
              key={activeStage}
            >
              <span className="detail-index">
                {String(activeStage + 1).padStart(2, "0")} /{" "}
                {String(lifecycle.length).padStart(2, "0")}
              </span>
              <h3>{lifecycle[activeStage].title}</h3>
              <p>{lifecycle[activeStage].body}</p>
              <code>{lifecycle[activeStage].evidence}</code>
            </div>
          </div>
        </section>

        <section className="story-section security-section" id="security">
          <div className="security-heading reveal">
            <div className="section-label">
              <span>03</span>
              Safety
            </div>
            <h2>Freedom inside hard boundaries.</h2>
            <p>
              Forge treats isolation, explicit capability, and audit evidence
              as architecture—not as promises added after execution.
            </p>
          </div>
          <div className="guardrail-list">
            {guardrails.map((item) => (
              <article className="reveal" key={item.title}>
                <span>{item.number}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <i aria-hidden="true">✓</i>
              </article>
            ))}
          </div>
        </section>

        <section
          className="story-section architecture-section"
          id="architecture"
        >
          <div className="architecture-heading reveal">
            <div className="section-label">
              <span>04</span>
              Architecture
            </div>
            <h2>A system of focused engines.</h2>
            <p>
              Durable events keep context, planning, execution, verification,
              and patch creation independent—without hiding the path between them.
            </p>
          </div>

          <div className="topology reveal" aria-label="Forge service topology">
            <div className="topology-node topology-request">
              <span>Ingress</span>
              <strong>FastAPI Gateway</strong>
            </div>
            <div className="topology-line" aria-hidden="true" />
            <div className="topology-node topology-backbone">
              <span>Event backbone</span>
              <strong>Redis Streams</strong>
            </div>
            <div className="engine-grid">
              {[
                ["Context", "Repository memory"],
                ["Planning", "Task DAG"],
                ["Execution", "Sandbox changes"],
                ["Verification", "Checks + repair"],
                ["Patch", "Branch + PR"],
              ].map(([name, role]) => (
                <article key={name}>
                  <span>{role}</span>
                  <strong>{name}</strong>
                </article>
              ))}
            </div>
            <div className="topology-line" aria-hidden="true" />
            <div className="topology-node topology-store">
              <span>State + audit</span>
              <strong>PostgreSQL</strong>
            </div>
          </div>

          <div className="stack-line reveal" aria-label="Forge technology stack">
            {["Python 3.12", "FastAPI", "Next.js", "Redis", "PostgreSQL", "Docker"].map(
              (technology) => (
                <span key={technology}>{technology}</span>
              ),
            )}
          </div>
        </section>

        <section className="story-section source-section">
          <div className="source-copy reveal">
            <div className="section-label section-label-light">
              <span>05</span>
              Open source
            </div>
            <h2>See what Forge can do today.</h2>
            <p>
              Forge is an internal alpha. The repository is the most honest,
              current view of the architecture, implementation, and roadmap.
            </p>
          </div>
          <div className="source-actions reveal">
            <a
              className="button button-white"
              href={repositoryUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open the repository <span aria-hidden="true">↗</span>
            </a>
            <a
              className="source-readme"
              href={`${repositoryUrl}#readme`}
              target="_blank"
              rel="noreferrer"
            >
              Read the architecture
            </a>
          </div>
        </section>

        <footer className="forge-footer">
          <a className="brand footer-brand" href="#top">
            <span className="brand-mark" aria-hidden="true">
              F
            </span>
            <strong>Forge</strong>
          </a>
          <p>Intent becomes a plan. A plan becomes verified change.</p>
          <nav aria-label="Footer navigation">
            <a href="#platform">Platform</a>
            <a href="#workflow">Workflow</a>
            <a href="#security">Safety</a>
            <a href={repositoryUrl} target="_blank" rel="noreferrer">
              GitHub ↗
            </a>
          </nav>
        </footer>
      </div>
    </main>
  );
}
