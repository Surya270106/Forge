'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

type Issue = { number: number; title: string; body: string; labels: string[]; url: string };
type Workflow = { id: string; issue: Issue; state: string; plan_id: string | null; last_error: string | null; base_commit_sha: string; pull_request_url: string | null };

export function IssueToPrPanel({ repositoryId }: { repositoryId: string }) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selected, setSelected] = useState<Issue | null>(null);
  const [number, setNumber] = useState('');
  const [active, setActive] = useState<Workflow | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const requestKey = useRef<string | null>(null);
  const headers = useCallback(() => ({ 'X-Organization-Id': localStorage.getItem('forge_org_id') || '' }), []);
  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/repositories/${repositoryId}/issue-workflows`, { headers: headers() });
      if (!response.ok) throw new Error('Issue workflow history is unavailable.');
      const data = await response.json(); setWorkflows(data.workflows || []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Issue workflow history is unavailable.'); }
  }, [headers, repositoryId]);
  useEffect(() => { void load(); }, [load]);
  const browse = async () => {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/v1/repositories/${repositoryId}/issues`, { headers: headers() });
      if (!response.ok) throw new Error('GitHub issues are unavailable. Check your connection and repository access.');
      const data = await response.json(); setIssues(data.issues || []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'GitHub issues are unavailable.'); }
    finally { setBusy(false); }
  };
  const selectNumber = async () => {
    if (!/^\d+$/.test(number)) { setError('Enter a GitHub issue number.'); return; }
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/v1/repositories/${repositoryId}/issues/${number}`, { headers: headers() });
      if (!response.ok) throw new Error('This issue is closed, unavailable, or not accessible.');
      setSelected(await response.json()); requestKey.current = null;
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Issue is unavailable.'); }
    finally { setBusy(false); }
  };
  const capture = async () => {
    if (!selected) return;
    setBusy(true); setError('');
    requestKey.current ||= crypto.randomUUID();
    try {
      const response = await fetch(`/api/v1/repositories/${repositoryId}/issue-workflows`, {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_number: selected.number, idempotency_key: requestKey.current }),
      });
      if (!response.ok) throw new Error('Issue capture failed. Refresh the issue or re-import the repository if its base moved.');
      const workflow: Workflow = await response.json(); setActive(workflow); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Issue capture failed.'); }
    finally { setBusy(false); }
  };
  const plan = async () => {
    if (!active) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/v1/issue-workflows/${active.id}/plan`, { method: 'POST', headers: headers() });
      if (!response.ok) throw new Error('Planning failed. Check model availability and retry from this workflow.');
      const workflow: Workflow = await response.json(); setActive(workflow); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Planning failed.'); }
    finally { setBusy(false); }
  };
  return <section className="focus-panel compact-focus-panel" aria-label="GitHub issue to pull request">
    <div className="section-label"><span>Issue</span>GitHub issue to PR</div>
    <div>
      <h2>Start from an issue.</h2>
      <p>Capture an open GitHub issue against this imported revision. You review the plan, execution, exact patch, and publication as separate steps.</p>
      <button type="button" className="button button-primary" disabled={busy} onClick={browse}>Browse open issues</button>
      <label htmlFor="forge-issue-number">Or enter issue number</label>
      <input id="forge-issue-number" inputMode="numeric" value={number} onChange={event => setNumber(event.target.value)} />
      <button type="button" className="button button-primary" disabled={busy} onClick={selectNumber}>Load issue</button>
      {issues.length > 0 && <ul>{issues.map(issue => <li key={issue.number}><button type="button" disabled={busy} onClick={() => { setSelected(issue); requestKey.current = null; }}>#{issue.number} {issue.title}</button></li>)}</ul>}
      {selected && <article><h3>#{selected.number} {selected.title}</h3><p>{selected.body || 'No description provided.'}</p><p>{selected.labels.join(', ')}</p><button type="button" className="button button-primary" disabled={busy} onClick={capture}>Capture issue</button></article>}
      {active && <article><p>Workflow: {active.state.replaceAll('_', ' ')} · Base <code>{active.base_commit_sha.slice(0, 12)}</code></p>
        {active.last_error && <p role="alert">{active.last_error}</p>}
        {active.plan_id ? <Link href={`/tasks/${active.plan_id}`} className="button button-primary">Review plan and evidence →</Link> : <button type="button" className="button button-primary" disabled={busy} onClick={plan}>{busy ? 'Planning…' : 'Generate engineering plan'}</button>}
        {active.pull_request_url && <a href={active.pull_request_url} target="_blank" rel="noopener noreferrer">Confirmed GitHub pull request ↗</a>}
      </article>}
      {workflows.length > 0 && <div><h3>Issue workflows</h3><ul>{workflows.map(workflow => <li key={workflow.id}><button type="button" onClick={() => setActive(workflow)}>#{workflow.issue.number} {workflow.issue.title} · {workflow.state.replaceAll('_', ' ')}</button></li>)}</ul></div>}
      {error && <p role="alert" className="product-alert">{error}</p>}
    </div>
  </section>;
}
