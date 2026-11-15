"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "../components/AppShell";

type GitHubRepository = { name: string; owner: string; description?: string; clone_url: string; default_branch?: string; is_private: boolean };
type ImportedRepository = { id: string; name: string; owner: string; status: string; indexing_status?: string };

export default function RepositoriesPage() {
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]);
  const [imported, setImported] = useState<ImportedRepository[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [githubUnavailable, setGithubUnavailable] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const controller = new AbortController();
    const headers = { "X-Organization-Id": localStorage.getItem("forge_org_id") || "" };
    void Promise.all([
      fetch(`/api/v1/repositories/github-repos`, { signal: controller.signal }),
      fetch(`/api/v1/repositories/imported`, { headers, signal: controller.signal }),
    ]).then(async ([githubResponse, importedResponse]) => {
      if (importedResponse.ok) setImported((await importedResponse.json()).repositories || []);
      else setError("Imported repository status could not be loaded. Refresh before importing again.");
      if (githubResponse.status === 401 || githubResponse.status === 400 || githubResponse.status === 403) {
        setGithubUnavailable(true);
        setError("GitHub repository access is unavailable. Reconnect GitHub, then refresh this page.");
        return;
      }
      if (!githubResponse.ok) { setGithubUnavailable(true); setError("GitHub repositories could not be loaded. Refresh to try again."); return; }
      setRepositories((await githubResponse.json()).repositories || []);
    }).catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Repositories are unavailable."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [router]);

  const handleImport = async (repo: GitHubRepository) => {
    const orgId = localStorage.getItem("forge_org_id");
    if (!orgId) { setError("Select a workspace before importing a repository."); return; }
    setImporting(`${repo.owner}/${repo.name}`); setError("");
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
      setError(typeof error.detail === "string" ? error.detail : `Import could not start (${response.status}).`);
    } catch { setError("Import could not start. Check the connection and try again."); }
    finally { setImporting(null); }
  };

  const filtered = useMemo(() => repositories.filter((repo) => `${repo.owner}/${repo.name}`.toLowerCase().includes(search.toLowerCase())), [repositories, search]);
  const visibleImported = useMemo(() => imported.filter((repo) => `${repo.owner}/${repo.name}`.toLowerCase().includes(search.toLowerCase())), [imported, search]);

  return (
    <AppShell><div className="page-frame">
      <Link href="/" className="back-link"><span>←</span> Workspace</Link>
      <header className="page-intro">
        <div className="section-label"><span>02</span>Repository ingress</div>
        <h1>Bring the codebase<br />into context.</h1>
        <p>Select a GitHub repository. Forge will import its source, preserve the default branch, and prepare it for indexing.</p>
      </header>
      {error && <p className="product-alert" role="alert">{error} {githubUnavailable && <Link href="/login">Reconnect GitHub →</Link>}</p>}
      <div className="page-toolbar">
        <label className="search-field"><span>Search</span><input type="search" placeholder="Repository name or owner" value={search} onChange={(e) => setSearch(e.target.value)} /><i>⌕</i></label>
        <span className="toolbar-count">{loading ? "—" : String(githubUnavailable ? visibleImported.length : filtered.length).padStart(2, "0")} available</span>
      </div>
      <section className="data-ledger" aria-label="GitHub repositories">
        <div className="data-ledger-head repo-ledger-grid"><span>Repository</span><span>Visibility</span><span>Branch</span><span>Action</span></div>
        {loading ? <div className="data-state"><span className="loading-orbit" />Reading GitHub repositories</div> :
          githubUnavailable && visibleImported.length ? visibleImported.map((repo, index) => <article className="data-row repo-ledger-grid" key={repo.id}><div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{repo.owner}/{repo.name}</h2><p>Imported · {repo.status.replaceAll("_", " ").toLowerCase()}</p></div></div><span className="mono-value">Forge workspace</span><code>—</code><Link className="row-action" href={`/repositories/${repo.id}`}>Open <span>→</span></Link></article>) :
          filtered.length === 0 ? <div className="data-state">{githubUnavailable ? "GitHub discovery is unavailable. No imported repositories match this search." : repositories.length ? "No repositories match this search." : "No repositories were returned by GitHub."}</div> :
          filtered.map((repo, index) => {
            const existing = imported.find((item) => item.owner === repo.owner && item.name === repo.name);
            return <article className="data-row repo-ledger-grid" key={`${repo.owner}/${repo.name}`}>
              <div className="data-primary"><i>{String(index + 1).padStart(2, "0")}</i><div><h2>{repo.owner}/{repo.name}</h2><p>{existing ? `Forge: ${existing.status.replaceAll("_", " ").toLowerCase()}${existing.indexing_status ? ` · index ${existing.indexing_status.replaceAll("_", " ").toLowerCase()}` : ""}` : repo.description || "Not imported into Forge."}</p></div></div>
              <span className="mono-value">{repo.is_private ? "Private" : "Public"}</span><code>{repo.default_branch || "Branch unavailable"}</code>
              {existing ? <Link className="row-action" href={`/repositories/${existing.id}`}>Open <span>→</span></Link> : <button className="row-action" type="button" disabled={importing === `${repo.owner}/${repo.name}`} onClick={() => handleImport(repo)}>{importing === `${repo.owner}/${repo.name}` ? "Importing…" : "Import"} <span>→</span></button>}
            </article>;
          })}
      </section>
    </div></AppShell>
  );
}
