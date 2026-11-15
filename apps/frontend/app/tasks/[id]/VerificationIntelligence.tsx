'use client';

import { useCallback, useEffect, useState } from 'react';

type Suggestion = { path: string; score: number; confidence: string; scope: string; reason_codes: string[]; source_paths: string[] };
type Decision = { current: boolean; strategy: string; snapshot_id: string | null; changed_paths: string[];
  suggested_tests: Suggestion[]; selected_verifiers: string[]; deferred_verifiers: { id: string; reason: string }[];
  verifier_targets: Record<string, string>; selected_verifier_reasons: Record<string, string>;
  fallback_reasons: string[]; flight_recorder_event_id: string | null };
type Intelligence = { job: { id: string; status: string } | null; plan: Decision | null;
  results: { id: string; verifier: string; status: string; exit_code: number | null; duration_ms: number | null }[];
  results_truncated: boolean };
type Preview = { current: boolean; configuration_checked: boolean; changed_paths: string[];
  suggested_tests: Suggestion[]; fallback_reasons: string[] };

export function VerificationIntelligence({ executionId, authHeaders }: {
  executionId: string; authHeaders: () => Record<string, string>;
}) {
  const [intelligence, setIntelligence] = useState<Intelligence | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setError('');
    try {
      const base = `/api/v1/verifications/executions/${executionId}/intelligence`;
      const response = await fetch(base, { headers: authHeaders(), credentials: 'include' });
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403
        ? 'Sign in to an authorized workspace to view verification decisions.' : 'Verification decisions are unavailable.');
      const body: Intelligence = await response.json();
      setIntelligence(body);
      if (!body.plan) {
        const previewResponse = await fetch(`${base}/preview`, { headers: authHeaders(), credentials: 'include' });
        setPreview(previewResponse.ok ? await previewResponse.json() : null);
      } else setPreview(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Verification decisions are unavailable.');
    } finally { setLoading(false); }
  }, [authHeaders, executionId]);
  useEffect(() => { void load(); }, [load]);

  const plan = intelligence?.plan;
  const suggestions = plan?.suggested_tests ?? preview?.suggested_tests ?? [];
  const reasons = plan?.fallback_reasons ?? preview?.fallback_reasons ?? [];
  return <article aria-label="Verification Intelligence">
    <h3>Verification Intelligence</h3>
    <p>Suggested tests are predictions. Command results below are the only recorded execution outcomes; no per-test coverage is claimed.</p>
    <button type="button" onClick={() => void load()}>Refresh decisions</button>
    {loading && <p aria-busy="true">Loading verification decisions…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && <>
      <p>{plan ? `Persisted ${plan.strategy.toLowerCase().replaceAll('_', ' ')} decision` : preview ? 'Preview only; worker configuration has not been inspected' : 'No prepared change evidence or selection decision yet'}.
        {plan && !plan.current ? ' The saved decision refers to a stale patch digest.' : ''}</p>
      {(plan || preview) && <><p>Changed paths: {(plan?.changed_paths ?? preview?.changed_paths ?? []).join(', ') || 'none recorded'}.</p>
        <p>Fallback: {reasons.length ? reasons.join(', ') : 'none'}.</p>
        <h4>Potentially relevant tests</h4>
        {suggestions.length ? <ul>{suggestions.map(test => <li key={test.path}><code>{test.path}</code> · {test.scope.toLowerCase()} · {test.confidence.toLowerCase()} confidence · {test.reason_codes.join(', ')} from {test.source_paths.join(', ')}</li>)}</ul> : <p>No test association was established.</p>}
      </>}
      {plan && <><h4>Configured checks selected</h4><ul>{plan.selected_verifiers.map(id => {
        const result = intelligence?.results.find(item => item.verifier === id);
        const state = result?.status ?? (intelligence?.job?.status === 'PENDING' ? 'QUEUED' : intelligence?.job?.status === 'RUNNING' ? 'NOT YET RECORDED' : 'NEVER EXECUTED');
        return <li key={id}><code>{id}</code> · {plan.verifier_targets[id] ?? 'configured check'} · {plan.selected_verifier_reasons[id]} · {state}{result?.duration_ms != null ? ` · ${result.duration_ms} ms` : ''}</li>;
      })}</ul>
        {plan.deferred_verifiers.length > 0 && <><h4>Deferred configured checks</h4><ul>{plan.deferred_verifiers.map(item => <li key={item.id}><code>{item.id}</code> · {item.reason}</li>)}</ul></>}
        {plan.flight_recorder_event_id && <p>Decision event <code>{plan.flight_recorder_event_id.slice(0, 12)}</code> in Flight Recorder.</p>}
      </>}
      <h4>Actual command results</h4>
      {intelligence?.results.length ? <ul>{intelligence.results.map(result => <li key={result.id}><code>{result.verifier}</code> · {result.status} · exit {result.exit_code ?? 'none'}</li>)}</ul> : <p>No command outcome is recorded.</p>}
      {intelligence?.results_truncated && <p>Only the first 100 command results are shown.</p>}
    </>}
  </article>;
}
