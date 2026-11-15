'use client';

import { useCallback, useEffect, useState } from 'react';

type CapsuleItem = { id: string; state: string; attempt: number; created_at: string; manifest_sha256: string };
type Artifact = { id: string; kind: string; sha256: string; size_bytes: number };
type Manifest = {
  execution_id: string; attempt: number; state: string; execution_status: string;
  base_commit_sha: string; patch_digest: string | null; change_set_id: string | null;
  verification_status: string | null; selection_plan_id: string | null;
  runtime: { forge_version: string | null; provider: string | null; model: string | null };
  sandbox: { image_ref: string | null; image_digest: string | null; network_disabled: boolean | null };
  artifacts: Artifact[]; missing_evidence: string[]; verification_results: { id: string; verifier: string; status: string }[];
};

export function RunCapsules({ executionId, authHeaders }: { executionId: string; authHeaders: () => Record<string, string> }) {
  const [items, setItems] = useState<CapsuleItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [hash, setHash] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (id?: string) => {
    setError('');
    try {
      const list = await fetch(`/api/v1/executions/${executionId}/capsules`, { headers: authHeaders(), credentials: 'include' });
      if (!list.ok) throw new Error(list.status === 401 || list.status === 403 ? 'Sign in to view run evidence.' : 'Run capsules are unavailable.');
      const body: { capsules: CapsuleItem[] } = await list.json();
      setItems(body.capsules);
      const next = id && body.capsules.some(item => item.id === id) ? id : body.capsules[0]?.id;
      setSelected(next ?? null);
      if (next) {
        const detail = await fetch(`/api/v1/executions/${executionId}/capsules/${next}`, { headers: authHeaders(), credentials: 'include' });
        if (!detail.ok) throw new Error(detail.status === 409 ? 'Capsule integrity check failed.' : 'Capsule details are unavailable.');
        const result: { manifest: Manifest; manifest_sha256: string } = await detail.json();
        setManifest(result.manifest);
        setHash(result.manifest_sha256);
      } else { setManifest(null); setHash(''); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Run capsules are unavailable.'); }
    finally { setLoading(false); }
  }, [authHeaders, executionId]);
  useEffect(() => { void load(); }, [load]);

  async function download(path: string, filename: string) {
    setError('');
    try {
      const response = await fetch(path, { headers: authHeaders(), credentials: 'include' });
      if (!response.ok) throw new Error(response.status === 409 ? 'Artifact integrity check failed.' : 'Download is unavailable.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
      URL.revokeObjectURL(url);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Download is unavailable.'); }
  }

  if (loading) return <section className="context-lens" aria-busy="true">Loading run capsules…</section>;
  return <section className="context-lens" aria-label="Run Capsules">
    <header><div><span className="eyebrow">Run Capsules · captured evidence</span><h2>Inspect this run.</h2><p>Immutable snapshots record facts available at each transition. They do not guarantee exact replay.</p></div><button type="button" onClick={() => void load(selected ?? undefined)}>Refresh</button></header>
    {error && <p role="alert">{error}</p>}
    {!items.length && <p>No capsule has been captured for this execution. Older runs may predate Run Capsules.</p>}
    {!!items.length && <><label htmlFor="run-capsule-choice">Captured snapshot</label> <select id="run-capsule-choice" value={selected ?? ''} onChange={event => void load(event.target.value)}>
      {items.map(item => <option key={item.id} value={item.id}>{item.state} · attempt {item.attempt} · {new Date(item.created_at).toLocaleString()}</option>)}
    </select></>}
    {manifest && selected && <div className="context-lens-grid">
      <article><h3>Identity and integrity</h3><p>Execution <code>{manifest.execution_id.slice(0, 12)}</code> · attempt {manifest.attempt} · {manifest.state}</p>
        <p>Execution {manifest.execution_status}; verification {manifest.verification_status ?? 'not recorded'}.</p>
        <p>Base revision <code>{manifest.base_commit_sha}</code></p><p>Patch digest <code>{manifest.patch_digest ?? 'not recorded'}</code></p>
        <p>Manifest SHA-256 <code>{hash}</code></p><button type="button" onClick={() => void download(`/api/v1/executions/${executionId}/capsules/${selected}/export`, `forge-capsule-${selected}.json`)}>Export manifest</button></article>
      <article><h3>Runtime and evidence</h3><p>Forge {manifest.runtime.forge_version ?? 'unknown'} · provider {manifest.runtime.provider ?? 'unknown'} · model {manifest.runtime.model ?? 'unknown'}</p>
        <p>Sandbox image {manifest.sandbox.image_ref ?? 'unknown'} · digest {manifest.sandbox.image_digest ?? 'unknown'}</p>
        <p>Change set {manifest.change_set_id ? <code>{manifest.change_set_id.slice(0, 12)}</code> : 'not recorded'}; selection plan {manifest.selection_plan_id ? <code>{manifest.selection_plan_id.slice(0, 12)}</code> : 'not recorded'}.</p>
        <p>See Context Lens and Flight Recorder for full change and event views.</p></article>
      <article><h3>Artifacts</h3>{manifest.artifacts.length ? <ul>{manifest.artifacts.map(artifact => <li key={artifact.id}>{artifact.kind} · {artifact.size_bytes} bytes · SHA-256 <code>{artifact.sha256.slice(0, 16)}…</code> <button type="button" onClick={() => void download(`/api/v1/executions/${executionId}/capsules/${selected}/artifacts/${artifact.id}`, `forge-${artifact.kind}-${artifact.id}.json`)}>Download</button></li>)}</ul> : <p>No bounded artifact was captured.</p>}
        <h4>Actual verification</h4>{manifest.verification_results.length ? <ul>{manifest.verification_results.map(result => <li key={result.id}>{result.verifier}: {result.status}</li>)}</ul> : <p>No command result is recorded. Suggestions alone are not verification.</p>}</article>
      <article><h3>Missing evidence and limits</h3>{manifest.missing_evidence.length ? <ul>{manifest.missing_evidence.map(item => <li key={item}>{item.replaceAll('_', ' ')}</li>)}</ul> : <p>No field is marked missing in this bounded snapshot.</p>}
        <p>External tools, mutable dependencies, model responses and host state may prevent exact reproduction. Export never reruns commands.</p></article>
    </div>}
  </section>;
}
