'use client';

import { useCallback, useEffect, useState } from 'react';
import { VerificationIntelligence } from './VerificationIntelligence';
import { RunCapsules } from './RunCapsules';

type Hunk = { before_start: number; before_count: number; after_start: number; after_count: number };
type FileChange = { mutation_id: string; task_node_id: string; path: string; type: string; hunks: Hunk[]; additions: number; deletions: number };
type Evidence = { node_key: string; depth: number; classification: string; snapshot_id: string; via: { kind: string; evidence_path: string; evidence_line: number; resolution: string; confidence: string }[] };
type Context = {
  execution: { id: string; status: string; base_commit_sha: string | null };
  change_set: { id: string; review_digest: string; files: FileChange[]; additions: number; deletions: number } | null;
  atlas: { base_snapshot_id: string | null; post_snapshot_id: string | null; direct_symbols: { mutation_id: string; name: string; kind: string; path: string; classification: string }[]; impacted: Evidence[]; relevant_tests: Evidence[]; unresolved_files: string[]; truncated: boolean };
  verification: { jobs: { id: string; status: string }[]; results: { id: string; job_id: string; verifier: string; status: string; exit_code: number | null; duration_ms: number | null }[]; summary: { relevant_tests: number; selected_tests: number | null; executed_commands: number; passed_commands: number; failed_commands: number; skipped_commands: number; relevant_tests_executed: number | null; coverage_claimed: boolean }; truncated: boolean };
  review: { status: string; current: boolean; approved: boolean; reviewer_id: string | null; publication: string; pull_request_url: string | null } | null;
  timeline: { events: { id: string; sequence: number; type: string }[]; next_cursor: number | null };
};

export function ContextLens({ executionId, authHeaders }: { executionId: string; authHeaders: () => Record<string, string> }) {
  const [data, setData] = useState<Context | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [cursor, setCursor] = useState(0);
  const load = useCallback(async (next = 0) => {
    setError('');
    try {
      const response = await fetch(`/api/v1/executions/${executionId}/context?cursor=${next}`, { headers: authHeaders(), credentials: 'include' });
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Sign in to an authorized workspace to view evidence.' : 'Change evidence is unavailable.');
      const body: Context = await response.json();
      setData(body);
      setCursor(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Change evidence is unavailable.');
    } finally {
      setLoading(false);
    }
  }, [authHeaders, executionId]);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <section className="context-lens" aria-busy="true">Loading change evidence…</section>;
  if (error) return <section className="context-lens"><p role="alert">{error}</p><button type="button" onClick={() => void load(cursor)}>Retry</button></section>;
  if (!data) return null;
  const { change_set: change, atlas, verification, review } = data;
  return <section className="context-lens" aria-label="Context Lens">
    <header><div><span className="eyebrow">Context Lens · evidence</span><h2>What changed, and what was checked?</h2><p>Predicted impact and recorded verification are shown separately.</p></div><button type="button" onClick={() => void load(cursor)}>Refresh evidence</button></header>
    <div className="context-lens-grid">
      <article><h3>Change and provenance</h3><p>Execution <code>{data.execution.id}</code> · {data.execution.status}</p><p>Base commit <code>{data.execution.base_commit_sha?.slice(0, 12) ?? 'not recorded'}</code></p>
        {change ? <><p>Patch digest <code>{change.review_digest.slice(0, 16)}…</code> · {change.files.length} edit records · +{change.additions}/−{change.deletions}</p>
          <ul>{change.files.map(file => <li key={file.mutation_id}><code>{file.path}</code> · {file.type} · +{file.additions}/−{file.deletions}<br /><small>Operation {file.task_node_id.slice(0, 12)} · {file.hunks.map(h => `−${h.before_start},${h.before_count} +${h.after_start},${h.after_count}`).join('; ')}</small></li>)}</ul></>
          : <p>No prepared change set is recorded for this execution. Older patches may predate Context Lens.</p>}</article>
      <article><h3>Structural impact · inferred</h3><p>Base Atlas snapshot: {atlas.base_snapshot_id ? <code>{atlas.base_snapshot_id.slice(0, 12)}</code> : 'not available'}. Post-change snapshot: {atlas.post_snapshot_id ? 'available' : 'not indexed'}.</p>
        {atlas.direct_symbols.length > 0 && <><h4>Changed regions overlapping base symbols</h4><ul>{atlas.direct_symbols.map((symbol, index) => <li key={`${symbol.mutation_id}-${index}`}>{symbol.kind} <code>{symbol.name}</code> in {symbol.path}</li>)}</ul></>}
        {atlas.impacted.length > 0 && <><h4>Potential downstream impact</h4><ul>{atlas.impacted.map(item => <li key={item.node_key}><code>{item.node_key}</code> · depth {item.depth} · {item.via.map(edge => `${edge.kind} ${edge.resolution}/${edge.confidence} at ${edge.evidence_path}:${edge.evidence_line}`).join(' → ')}</li>)}</ul></>}
        <h4>Potentially relevant tests</h4>{atlas.relevant_tests.length ? <ul>{atlas.relevant_tests.map(item => <li key={item.node_key}><code>{item.node_key}</code> · inferred association; execution unknown</li>)}</ul> : <p>No test association was found in the matching base snapshot.</p>}
        {atlas.unresolved_files.length > 0 && <p>Files absent from the base graph: {atlas.unresolved_files.join(', ')}</p>}{atlas.truncated && <p>Impact results reached the query limit.</p>}</article>
      <article><h3>Actual verification · command results</h3><p>{verification.summary.executed_commands} completed commands · {verification.summary.passed_commands} passed · {verification.summary.failed_commands} failed · {verification.summary.skipped_commands} explicitly skipped</p>
        <p>{verification.summary.relevant_tests} potentially relevant tests. Individual test-case outcomes and coverage are not recorded; selected commands and their results appear below.</p>
        {verification.results.length ? <ul>{verification.results.map(result => <li key={result.id}>{result.verifier}: <strong>{result.status}</strong> · exit {result.exit_code ?? 'none'}{result.duration_ms != null ? ` · ${result.duration_ms} ms` : ''}</li>)}</ul> : <p>No verification command result was recorded.</p>}
        {verification.truncated && <p>Verification history is truncated; counts above describe the displayed results.</p>}</article>
      <article><h3>Review and publication</h3>{review ? <><p>Patch {review.status} · digest {review.current ? 'matches captured and current evidence' : 'does not match captured or current evidence'}</p><p>Approval: {review.approved ? `recorded by ${review.reviewer_id}` : 'not currently valid'}</p><p>Publication: {review.publication}</p>{review.pull_request_url && <a href={review.pull_request_url} target="_blank" rel="noreferrer">Open pull request</a>}</> : <p>No patch review is recorded.</p>}
        <h4>Flight Recorder references</h4><ul>{data.timeline.events.map(event => <li key={event.id}>#{event.sequence} {event.type} · <code>{event.id.slice(0, 12)}</code></li>)}</ul>{data.timeline.next_cursor != null && <button type="button" onClick={() => void load(data.timeline.next_cursor!)}>More events</button>}</article>
      <VerificationIntelligence executionId={executionId} authHeaders={authHeaders} />
      <RunCapsules executionId={executionId} authHeaders={authHeaders} />
    </div>
  </section>;
}
