"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "../components/AppShell";

type GitHubRepository = { name: string; owner: string; description?: string; clone_url: string; default_branch?: string; is_private: boolean };

export default function RepositoriesPage() {
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const router = useRouter();

  useEffect(() => {
    fetch(`/api/v1/repositories/github-repos`).then(async (response) => {
      if (response.status === 401 || response.status === 400) { router.push("/login"); return; }
      if (response.ok) { const data = await response.json(); setRepositories(data.repositories || []); }
    }).catch(console.error).finally(() => setLoading(false));
  }, [router]);

  const handleImport = async (repo: GitHubRepository) => {
    const orgId = localStorage.getItem("forge_org_id");
    if (!orgId) { window.alert("No workspace selected. Please sign in again."); return; }
    setImporting(repo.name);
    try {
      const response = await fetch(`/api/v1/repositories/import`, {
        method: "POST",
        headers: { "X-Organization-Id": orgId, "Content-Type": "application/json" },
        body: JSON.stringify({ clone_url: repo.clone_url, owner: repo.owner, name: repo.name, branch: repo.default_branch || "main", is_private: repo.is_private }),
      });
      if (response.ok) { 
        const data = await response.json();
        router.push(`/repositories/${data.repository_id}`); 
        return; 
      }
      const error = await response.json().catch(() => ({}));
      window.alert(`Failed to import: ${error.detail || response.status}`);
    } catch (error) { console.error(error); window.alert("An error occurred during import."); }
    finally { setImporting(null); }
  };

  const filtered = useMemo(() => repositories.filter((repo) => `${repo.owner}/${repo.name}`.toLowerCase().includes(search.toLowerCase())), [repositories, search]);

  return (
    <AppShell><div className="page-frame">
      <Link href="/" className="back-link"><span>←</span> Workspace</Link>
      <header className="page-intro">
        <div className="section-label"><span>02</span>Repository ingress</div>
        <h1>Bring the codebase<br />into context.</h1>
        <p>Select a GitHub repository. Forge will import its source, preserve the default branch, and prepare it for indexing.</p>
      </header>
      <div className="page-toolbar">
        <label className="search-field"><span>Search</span><input type="search" placeholder="Repository name or owner" value={search} onChange={(e) => setSearch(e.target.value)} /><i>⌕</i></label>
        <span className="toolbar-count">{loading ? "—" : String(filtered.length).padStart(2, "0")} available</span>
      </div>
      <section className="data-ledger" aria-label="GitHub repositories">
        <div className="data-ledger-head repo-ledger-grid"><span>Repository</span><span>Visibility</span><span>Branch</span><span>Action</span></div>
        {loading ? <div className="data-state"><span className="loading-orbit" />Reading GitHub repositories</div> :
          filtered.length === 0 ? <div className="data-state">{repositories.length ? "No repositories match this search." : "No repositories were returned by GitHub."}</div> :
          filtered.map((repo, index) => (
            <article className="data-row repo-ledger-grid" key={`${repo.owner}/${repo.name}`}>
              <div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{repo.owner}/{repo.name}</h2><p>{repo.description || "No description provided."}</p></div></div>
              <span className="mono-value">{repo.is_private ? "Private" : "Public"}</span><code>{repo.default_branch || "main"}</code>
              <button className="row-action" type="button" disabled={importing === repo.name} onClick={() => handleImport(repo)}>{importing === repo.name ? "Importing…" : "Import"} <span>→</span></button>
            </article>
          ))}
      </section>
    </div></AppShell>
  );
}
