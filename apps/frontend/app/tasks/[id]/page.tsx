'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Check, LoaderCircle, Play, Square } from 'lucide-react';

import { env } from '../../../config/env';
import { AppShell } from '../../components/AppShell';
import { FlightRecorder } from './FlightRecorder';
import { ContextLens } from './ContextLens';

type PlanNode = {
  id: string;
  action_type: string;
  target: string;
  parameters: Record<string, unknown>;
};

type Plan = {
  id: string;
  repository_id: string;
  status: string;
  intent: string;
  nodes: PlanNode[];
  created_at?: string;
};

type Mutation = {
  id: string;
  file_path: string;
  mutation_type: string;
  diff_hunk: string;
};

type Verification = { id: string; status: string; results?: {
  verifier: string; status: string; exit_code: number | null; duration_ms?: number | null; attempt?: number; blocking?: boolean;
  stdout: string | null; stderr: string | null; diagnostics: { file?: string; line?: number; message?: string }[];
}[] };
type Repair = { id: string; status: string; attempt_number: number; repair_plan_id: string | null; error_message: string | null; feedback: string | null };
type Patch = {
  id: string;
  status: string;
  publish_status: string;
  publish_error: string | null;
  pull_request_url: string | null;
  files_changed?: number;
  total_additions?: number;
  total_deletions?: number;
  base_commit_sha?: string | null;
};
type PatchReview = { review_digest: string; base_commit_sha: string; changes: { path: string; diff: string }[] };
type IssueWorkflow = { id: string; state: string; base_commit_sha: string; issue: { number: number; title: string; body: string; url: string; labels: string[] } };
type ActiveTab = 'plan' | 'execution' | 'review' | 'context';

function nodeTitle(node: PlanNode) {
  if (node.action_type === 'edit_file') return `Edit ${node.target}`;
  if (node.action_type === 'command') return `Run command in ${node.target}`;
  return `${node.action_type.replaceAll('_', ' ')} · ${node.target}`;
}

function nodeDetail(node: PlanNode) {
  const changes = node.parameters?.changes;
  const command = node.parameters?.command;

  if (typeof changes === 'string') return changes;
  if (typeof command === 'string') return command;
  return JSON.stringify(node.parameters, null, 2);
}

function DiffFile({ diff }: { diff: string }) {
  return <pre className="review-diff" aria-label="Unified diff">{diff.split('\n').map((line, index) => {
    const kind = line.startsWith('+') && !line.startsWith('+++') ? 'added' : line.startsWith('-') && !line.startsWith('---') ? 'removed' : line.startsWith('@@') ? 'hunk' : '';
    return <span className={kind} key={index}>{line || ' '}{'\n'}</span>;
  })}</pre>;
}

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [issueWorkflow, setIssueWorkflow] = useState<IssueWorkflow | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const [cancellationRequested, setCancellationRequested] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [executionLookupReady, setExecutionLookupReady] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [mutations, setMutations] = useState<Mutation[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [repair, setRepair] = useState<Repair | null>(null);
  const [patch, setPatch] = useState<Patch | null>(null);
  const [patchReview, setPatchReview] = useState<PatchReview | null>(null);
  const [selectedDiffPath, setSelectedDiffPath] = useState<string | null>(null);
  const [patchBusy, setPatchBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>('plan');
  const [error, setError] = useState('');

  const authHeaders = useCallback(() => {
    const orgId = localStorage.getItem('forge_org_id');

    return {
      'X-Organization-Id': orgId || '',
    };
  }, []);

  const fetchPlan = useCallback(async () => {
    setExecutionLookupReady(false);
    try {
      const response = await fetch(
        `/api/v1/plans/${id}`,
        { headers: authHeaders() },
      );

      if (!response.ok) throw new Error('The plan could not be loaded.');
      setPlan(await response.json());
      const issueResponse = await fetch(`/api/v1/plans/${id}/issue-workflow`, { headers: authHeaders() });
      if (issueResponse.ok) setIssueWorkflow(await issueResponse.json());
      const latest = await fetch(`/api/v1/executions/plans/${id}/latest`, { headers: authHeaders() });
      if (!latest.ok && latest.status !== 404) throw new Error('Execution status is unavailable. Refresh before starting work.');
      if (latest.ok) {
        const job = await latest.json();
        setExecutionId(job.id);
        setExecutionStatus(job.status);
        setCancellationRequested(Boolean(job.cancellation_requested_at));
        setExecuting(job.status === 'PENDING' || job.status === 'RUNNING');
      }
      setExecutionLookupReady(true);
      setError('');
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The plan could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, [authHeaders, id]);

  const fetchExecution = useCallback(
    async (jobId: string) => {
      try {
        const [jobResponse, logsResponse] = await Promise.all([
          fetch(
            `/api/v1/executions/${jobId}`,
            { headers: authHeaders() },
          ),
          fetch(
            `/api/v1/executions/${jobId}/logs`,
            { headers: authHeaders() },
          ),
        ]);

        if (jobResponse.status === 401 || logsResponse.status === 401) {
          window.location.assign('/login');
          return;
        }
        if (!jobResponse.ok || !logsResponse.ok) throw new Error('Execution status is unavailable.');

        if (jobResponse.ok) {
          const job = await jobResponse.json();
          setExecutionStatus(job.status);
          setCancellationRequested(Boolean(job.cancellation_requested_at));

          if (job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
            setExecuting(false);

            const mutationResponse = await fetch(
              `/api/v1/executions/${jobId}/mutations`,
              { headers: authHeaders() },
            );

            if (mutationResponse.ok) {
              const mutationPayload = await mutationResponse.json();
              setMutations(mutationPayload.mutations || []);
            }
          }
        }

        if (logsResponse.ok) {
          const logPayload = await logsResponse.json();
          setLogs(
            logPayload.map((entry: { message: string }) => entry.message).slice(-1000),
          );
        }
      } catch {
        setError('Execution status is temporarily unavailable. Forge will keep trying.');
      }
    },
    [authHeaders],
  );

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  useEffect(() => {
    if (executionId && !executing) void fetchExecution(executionId);
  }, [executionId, executing, fetchExecution]);

  useEffect(() => {
    if (!executionId || executionStatus !== 'COMPLETED') return;
    const refresh = async () => {
      const headers = authHeaders();
      const [verificationResponse, patchResponse] = await Promise.all([
        fetch(`/api/v1/verifications/executions/${executionId}/latest`, { headers }),
        fetch(`/api/v1/patches/executions/${executionId}`, { headers }),
      ]);
      if (verificationResponse.ok) {
        const latestVerification: Verification = await verificationResponse.json();
        setVerification(latestVerification);
        if (latestVerification.status === 'FAILED') {
          const repairResponse = await fetch(`/api/v1/verifications/${latestVerification.id}/repair`, { headers });
          if (repairResponse.ok) setRepair(await repairResponse.json());
        }
      }
      if (patchResponse.ok) setPatch(await patchResponse.json());
    };
    void refresh().catch(() => setError('Review status is temporarily unavailable.'));
    const timer = window.setInterval(() => void refresh().catch(() => {}), 5000);
    return () => window.clearInterval(timer);
  }, [executionId, executionStatus, authHeaders]);

  const loadPatchReview = async (patchId: string) => {
    const response = await fetch(`/api/v1/patches/${patchId}/review`, { headers: authHeaders() });
    if (!response.ok) {
      setPatchReview(null);
      setSelectedDiffPath(null);
      throw new Error('The patch review is stale or unavailable. Refresh it before approval.');
    }
    const review: PatchReview = await response.json();
    setPatchReview(review);
    setSelectedDiffPath(review.changes[0]?.path || null);
  };

  const preparePatch = async () => {
    if (!executionId) return;
    setPatchBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/v1/patches/executions/${executionId}/generate`, {
        method: 'POST', headers: authHeaders(),
      });
      if (!response.ok) throw new Error('Forge could not prepare a reviewable patch.');
      const prepared = await response.json();
      setPatch(prepared);
      await loadPatchReview(prepared.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Patch review is unavailable.');
    } finally { setPatchBusy(false); }
  };

  const approvePatch = async () => {
    if (!patch || !patchReview) return;
    setPatchBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/v1/patches/${patch.id}/accept`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_digest: patchReview.review_digest }),
      });
      if (!response.ok) throw new Error('Approval was rejected. Refresh the patch review.');
      setPatch(await response.json());
    } catch (cause) {
      setPatchReview(null);
      setSelectedDiffPath(null);
      setError(cause instanceof Error ? cause.message : 'Patch approval failed.');
    } finally { setPatchBusy(false); }
  };

  const publishPatch = async () => {
    if (!patch) return;
    setPatchBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/v1/patches/${patch.id}/publish`, {
        method: 'POST', headers: authHeaders(),
      });
      if (!response.ok) throw new Error('Publication was not queued. Check verification and GitHub access.');
      setPatch(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not request publication.');
    } finally { setPatchBusy(false); }
  };

  const updateRepair = async (action: 'plan' | 'cancel') => {
    if (!repair) return;
    setPatchBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/v1/verifications/repairs/${repair.id}/${action}`, {
        method: 'POST', headers: authHeaders(),
      });
      if (!response.ok) throw new Error('The repair request could not be completed.');
      setRepair({ ...repair, status: (await response.json()).status });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Repair request failed.');
    } finally { setPatchBusy(false); }
  };

  useEffect(() => {
    if (!executionId || !executing) return;

    void fetchExecution(executionId);
    const statusTimer = window.setInterval(() => void fetchExecution(executionId), 5000);
    const wsUrl = `${env.NEXT_PUBLIC_EVENT_URL}/api/v1/executions/${executionId}/ws`;
    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let retries = 0;

    const connect = async () => {
      try {
        const response = await fetch(`/api/v1/executions/${executionId}/ws-ticket`, {
          method: 'POST',
          headers: authHeaders(),
        });
        if (!response.ok) throw new Error('Live log authorization failed.');
        const { ticket } = await response.json();
        if (typeof ticket !== 'string') throw new Error('Invalid live log ticket.');
        if (closed) return;
        socket = new WebSocket(wsUrl, ['forge.v1', `forge.ticket.${ticket}`]);
        socket.onmessage = onMessage;
        socket.onclose = () => {
          if (!closed && retries++ < 3) reconnectTimer = window.setTimeout(() => void connect(), 3000);
        };
      } catch {
        if (!closed) setError('Live logs are unavailable. Saved logs will continue to refresh.');
      }
    };

    const onMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data && data.message) {
          setLogs((prev) => {
            if (prev[prev.length - 1] === data.message) return prev;
            return [...prev, data.message].slice(-1000);
          });
        }
      } catch {
        setError('A live log message could not be read. Saved logs will continue to refresh.');
      }
    };

    void connect();
    return () => {
      closed = true;
      window.clearInterval(statusTimer);
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [executionId, executing, fetchExecution, authHeaders]);

  const handleApprove = async () => {
    setApproving(true);
    setError('');

    try {
      const response = await fetch(
        `/api/v1/plans/${id}/approve`,
        {
          method: 'POST',
          headers: authHeaders(),
        },
      );

      if (!response.ok) throw new Error('Forge could not approve this plan.');
      await fetchPlan();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Forge could not approve this plan.',
      );
    } finally {
      setApproving(false);
    }
  };

  const handleExecute = async () => {
    setExecuting(true);
    setExecutionStatus('PENDING');
    setCancellationRequested(false);
    setLogs([]);
    setMutations([]);
    setError('');
    setActiveTab('execution');

    try {
      const response = await fetch(
        `/api/v1/executions/plans/${id}`,
        {
          method: 'POST',
          headers: {
            ...authHeaders(),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({}),
        },
      );

      if (!response.ok) throw new Error('Forge could not start this execution.');
      const execution = await response.json();
      setExecutionId(execution.id);
      setExecutionStatus(execution.status || 'PENDING');
    } catch (requestError) {
      setExecuting(false);
      setExecutionStatus(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Forge could not start this execution.',
      );
    }
  };

  const handleCancelExecution = async () => {
    if (!executionId || !window.confirm(executionStatus === 'COMPLETED'
      ? 'Cancel the active verification? Its sandbox command will be stopped.'
      : 'Cancel this execution? Running commands will be stopped.')) return;
    setCancelBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/v1/executions/${executionId}/cancel`, {
        method: 'POST', headers: authHeaders(),
      });
      if (response.status === 401) {
        window.location.assign('/login');
        return;
      }
      if (!response.ok) throw new Error('The cancellation request could not be saved.');
      const result = await response.json();
      setExecutionStatus(result.status);
      setCancellationRequested(result.cancellation_status === 'requested');
      if (result.status === 'CANCELLED') setExecuting(false);
      if (result.status === 'COMPLETED' && result.cancellation_status === 'completed') {
        setVerification((current) => current ? { ...current, status: 'CANCELLED' } : current);
      }
      if (result.cancellation_status === 'not_cancellable') setError('This execution has already finished.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The cancellation request failed.');
    } finally {
      setCancelBusy(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="page-frame full-page-state data-state">
          <LoaderCircle aria-hidden="true" size={20} className="loading-orbit" />
          Resolving execution plan
        </div>
      </AppShell>
    );
  }

  if (!plan) {
    return (
      <AppShell>
        <div className="page-frame full-page-state data-state">
          {error || 'Plan not found.'}
        </div>
      </AppShell>
    );
  }

  const status = executionStatus || plan.status;
  const canApprove = plan.status === 'PENDING_APPROVAL';
  const canExecute = plan.status === 'APPROVED' && executionStatus === null && executionLookupReady;
  const lifecycle = [
    { label: 'Plan', detail: plan.status === 'PENDING_APPROVAL' ? 'Needs approval' : plan.status.replaceAll('_', ' ').toLowerCase(), complete: plan.status === 'APPROVED' || Boolean(executionStatus) },
    { label: 'Execution', detail: executionStatus ? executionStatus.toLowerCase() : 'Not started', complete: executionStatus === 'COMPLETED' },
    { label: 'Verification', detail: verification?.status?.toLowerCase() || 'Not run', complete: verification?.status === 'PASSED' },
    { label: 'Review', detail: patch?.status?.replaceAll('_', ' ').toLowerCase() || 'Not prepared', complete: patch?.status === 'ACCEPTED' || patch?.status === 'COMMITTED' || patch?.status === 'PULL_REQUEST_CREATED' },
    { label: 'Publication', detail: patch?.publish_status?.replaceAll('_', ' ').toLowerCase() || 'Not requested', complete: patch?.publish_status === 'SUCCEEDED' },
  ];
  const selectedChange = patchReview?.changes.find((change) => change.path === selectedDiffPath) || patchReview?.changes[0];

  return (
    <AppShell>
      <main className="page-frame">
        <Link href={`/repositories/${plan.repository_id}`} className="back-link">
          <ArrowLeft aria-hidden="true" size={15} />
          Back to repository
        </Link>

        <section className="plan-header">
          <div className="eyebrow">
            <span />
            Execution plan
          </div>

          {plan.intent.length > 100 ? (
            <details className="plan-intent-details">
              <summary>
                <h1 className="long-intent">
                  {plan.intent.substring(0, 100)}... <span>(Show full intent)</span>
                </h1>
              </summary>
              <div className="intent-full">
                <p>{plan.intent}</p>
              </div>
            </details>
          ) : (
            <h1>{plan.intent}</h1>
          )}

          <div className="plan-state">
            <i>Current state</i>
            <strong>{status.replaceAll('_', ' ')}</strong>
            <code>{plan.id.slice(0, 12)}</code>
          </div>
        </section>

        {issueWorkflow && <section className="focus-panel compact-focus-panel" aria-label="Source GitHub issue">
          <div className="section-label"><span>Source</span>GitHub issue #{issueWorkflow.issue.number}</div>
          <div><h2>{issueWorkflow.issue.title}</h2><p>{issueWorkflow.issue.body || 'No issue description provided.'}</p>
            <p>Captured base <code>{issueWorkflow.base_commit_sha}</code> · {issueWorkflow.state.replaceAll('_', ' ')}</p>
            <a href={issueWorkflow.issue.url} target="_blank" rel="noopener noreferrer">View original issue ↗</a>
          </div>
        </section>}

        <ol className="task-lifecycle" aria-label="Task lifecycle">
          {lifecycle.map((stage) => <li key={stage.label} className={stage.complete ? 'is-complete' : ''}><strong>{stage.label}</strong><span>{stage.detail}</span></li>)}
        </ol>

        <nav className="segment-nav plan-segment-nav" aria-label="Plan views">
          <button
            type="button"
            className={activeTab === 'plan' ? 'is-active' : ''}
            onClick={() => setActiveTab('plan')}
          >
            <span>01</span>
            Plan
          </button>
          <button
            type="button"
            className={activeTab === 'execution' ? 'is-active' : ''}
            onClick={() => setActiveTab('execution')}
          >
            <span>02</span>
            Execution
          </button>
          <button type="button" className={activeTab === 'review' ? 'is-active' : ''} onClick={() => setActiveTab('review')}>
            <span>03</span>Change review
          </button>
          <button type="button" className={activeTab === 'context' ? 'is-active' : ''} onClick={() => setActiveTab('context')}>
            <span>04</span>Context Lens
          </button>
        </nav>

        {error && <p className="form-message form-error">{error}</p>}

        {activeTab === 'plan' ? (
          <section className="plan-map">
            <div className="plan-map-intro">
              <span>Verified action graph</span>
              <h2>Inspect every move before code changes.</h2>
              <p>
                Forge translates the intent into an explicit, reviewable sequence.
                Nothing enters the execution environment until you approve it.
              </p>
              <dl className="task-preflight"><div><dt>Repository</dt><dd><Link href={`/repositories/${plan.repository_id}`}>{plan.repository_id.slice(0, 12)} ↗</Link></dd></div><div><dt>Planned actions</dt><dd>{plan.nodes?.length ?? 0}</dd></div><div><dt>Worker</dt><dd>Availability unknown; queued work waits for a Docker worker.</dd></div></dl>

              {canApprove && (
                <button
                  type="button"
                  className="button button-white"
                  onClick={handleApprove}
                  disabled={approving}
                >
                  {approving ? (
                    <LoaderCircle aria-hidden="true" size={16} />
                  ) : (
                    <Check aria-hidden="true" size={16} />
                  )}
                  {approving ? 'Approving' : 'Approve plan'}
                </button>
              )}

              {canExecute && (
                <button
                  type="button"
                  className="button button-white"
                  onClick={handleExecute}
                  disabled={executing}
                >
                  <Play aria-hidden="true" size={15} />
                  Start execution
                </button>
              )}

              {executionStatus && (
                <button
                  type="button"
                  className="button button-white"
                  onClick={() => setActiveTab('execution')}
                >
                  View execution
                  <span aria-hidden="true">↗</span>
                </button>
              )}
            </div>

            <div className="plan-node-list">
              {plan.nodes?.length ? (
                plan.nodes.map((node, index) => (
                  <article key={node.id} className="plan-node">
                    <div>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <i>{node.action_type.replaceAll('_', ' ')}</i>
                    </div>
                    <h3>{nodeTitle(node)}</h3>
                    <pre>{nodeDetail(node)}</pre>
                  </article>
                ))
              ) : (
                <article className="plan-node">
                  <div>
                    <span>00</span>
                    <i>Plan payload</i>
                  </div>
                  <h3>No discrete task nodes were returned.</h3>
                  <pre>{JSON.stringify(plan, null, 2)}</pre>
                </article>
              )}
            </div>
          </section>
        ) : activeTab === 'execution' ? (
          <>
            <section className="execution-console">
              <header>
                <div>
                  <i />
                  <i />
                  <i />
                  <span>Forge terminal // isolated execution</span>
                </div>
                <div className="console-actions"><strong>{executionStatus === 'FAILED' && cancellationRequested ? 'Cancellation failed' : verification?.status === 'CANCELLED' ? 'Verification cancelled' : cancellationRequested && executionStatus === 'COMPLETED' ? 'Verification cancellation requested' : cancellationRequested && executionStatus === 'RUNNING' ? 'Cancellation requested' : executionStatus || 'Awaiting launch'}</strong><button type="button" disabled={!logs.length} onClick={() => void navigator.clipboard.writeText(logs.join('\n')).catch(() => setError('The logs could not be copied.'))}>Copy logs</button></div>
              </header>

              <div className="terminal-output" aria-live="polite">
                {logs.length ? (
                  logs.map((log, index) => (
                    <div key={`${index}-${log}`}>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <code>{log}</code>
                    </div>
                  ))
                ) : (
                  <p>{executionStatus === 'PENDING' ? 'Execution is queued. Waiting for a Docker worker to claim it.' : executionStatus === 'RUNNING' && cancellationRequested ? 'Stopping the running command and cleaning up its sandbox.' : executionStatus === 'RUNNING' ? 'The worker is running. Saved logs will appear here.' : executionStatus === 'FAILED' && cancellationRequested ? 'Cancellation could not be confirmed. Inspect the sandbox and saved timeline before retrying.' : executionStatus === 'FAILED' ? 'Execution failed. Inspect the saved logs and review the repository workspace before starting new work.' : executionStatus === 'CANCELLED' ? 'Execution was cancelled. Review the saved timeline before starting new work.' : 'No execution has started. Approve the plan, then start it from the Plan view.'}</p>
                )}

                {executing && (
                  <div className="terminal-pulse">
                    <span>--</span>
                    <code>Waiting for worker updates. Live connection loss does not change the job state.</code>
                  </div>
                )}
              </div>

              <footer>
                <p>
                  Execution runs inside Forge&apos;s isolated environment. Status,
                  logs, and resulting file mutations update here automatically.
                </p>

                {canExecute && (
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={handleExecute}
                    disabled={executing}
                  >
                    <Play aria-hidden="true" size={15} />
                    Start execution
                  </button>
                )}
                {executionId && (executionStatus === 'PENDING' || executionStatus === 'RUNNING' ||
                  (executionStatus === 'COMPLETED' && (verification?.status === 'PENDING' || verification?.status === 'RUNNING'))) && (
                  <button type="button" className="button button-white" onClick={() => void handleCancelExecution()}
                    disabled={cancelBusy || cancellationRequested}>
                    <Square aria-hidden="true" size={15} />
                    {cancellationRequested ? 'Stopping work…' : cancelBusy ? 'Requesting cancellation…' : executionStatus === 'COMPLETED' ? 'Cancel verification' : 'Cancel execution'}
                  </button>
                )}
              </footer>
            </section>

            {executionId && <FlightRecorder key={executionId} executionId={executionId}
              active={executing || verification?.status === 'PENDING' || verification?.status === 'RUNNING' || patch?.publish_status === 'QUEUED' || patch?.publish_status === 'RUNNING'}
              revision={`${verification?.status || ''}:${patch?.status || ''}:${patch?.publish_status || ''}`}
              authHeaders={authHeaders} />}

            {executionStatus === 'COMPLETED' && (
              <section className="mutation-section">
                <div className="mutation-heading">
                  <div className="eyebrow">
                    <span />
                    Applied mutations
                  </div>
                  <h2>Applied changes, file by file.</h2>
                  <p>
                    The execution finished. Review the mutations produced by the
                    approved plan; verification results are separate.
                  </p>
                </div>

                <div className="mutation-list">
                  {mutations.length ? (
                    mutations.map((mutation, index) => (
                      <article key={mutation.id}>
                        <header>
                          <span>{String(index + 1).padStart(2, '0')}</span>
                          <code>{mutation.file_path}</code>
                          <i>{mutation.mutation_type}</i>
                        </header>
                        <pre>{mutation.diff_hunk}</pre>
                      </article>
                    ))
                  ) : (
                    <article>
                      <header>
                        <span>00</span>
                        <code>No file mutations returned</code>
                        <i>Complete</i>
                      </header>
                    </article>
                  )}
                </div>
              </section>
            )}
          </>
        ) : activeTab === 'context' ? (
          executionId ? <ContextLens key={executionId} executionId={executionId} authHeaders={authHeaders} /> :
            <section className="context-lens"><p>Start an execution to collect change evidence.</p></section>
        ) : (
          <section className="mutation-section" aria-label="Change review and GitHub contribution">
            <div className="mutation-heading">
              <div className="eyebrow"><span />Review evidence</div>
              <h2>Review the change.</h2>
              <p>Execution, verification, approval, and GitHub publication are separate steps.</p>
            </div>
            <div className="mutation-list">
              <article>
                <header className="review-result-header"><code>Verification</code><i>{verification?.status || 'Awaiting result'}</i></header>
                {!verification && <p>No verification result is available yet. Execution completion alone does not mean the change passed verification.</p>}
                {verification?.results?.map((result) => (
                  <details key={result.verifier}>
                    <summary>{result.verifier}: {result.status} · exit {result.exit_code ?? 'not run'}{result.duration_ms != null ? ` · ${result.duration_ms} ms` : ''}{result.attempt ? ` · attempt ${result.attempt}` : ''}</summary>
                    {result.diagnostics?.map((finding, index) => (
                      <p key={`${result.verifier}-${index}`}>{finding.file || 'Check'}{finding.line ? `:${finding.line}` : ''}: {finding.message}</p>
                    ))}
                    {result.stdout && <pre>{result.stdout.slice(-10000)}</pre>}
                    {result.stderr && <pre>{result.stderr.slice(-10000)}</pre>}
                  </details>
                ))}
              </article>
              {repair && (
                <article>
                  <header className="review-result-header"><code>Repair attempt {repair.attempt_number} of 3</code><i>{repair.status.replaceAll('_', ' ')}</i></header>
                  {repair.feedback && <pre>{repair.feedback}</pre>}
                  {repair.error_message && <p role="alert">{repair.error_message}</p>}
                  {repair.status === 'ELIGIBLE' && (
                    <button type="button" className="button button-primary" disabled={patchBusy} onClick={() => void updateRepair('plan')}>
                      Request bounded repair plan
                    </button>
                  )}
                  {repair.repair_plan_id && <Link href={`/tasks/${repair.repair_plan_id}`}>Review repair plan →</Link>}
                  {(repair.status === 'PLANNING' || repair.status === 'AWAITING_APPROVAL') && (
                    <button type="button" className="button button-white" disabled={patchBusy} onClick={() => void updateRepair('cancel')}>
                      Cancel repair proposal
                    </button>
                  )}
                </article>
              )}
              {verification?.status === 'PASSED' && !patch && executionId && (
                <button type="button" className="button button-primary" disabled={patchBusy} onClick={preparePatch}>
                  Prepare change review
                </button>
              )}
              {patch && (
                <article>
                  <header className="review-result-header"><code>Patch {patch.id.slice(0, 12)}</code><i>{patch.status}</i></header>
                  <p>GitHub publication: {patch.publish_status.replaceAll('_', ' ')}</p>
                  {patch.publish_error && <p role="alert">{patch.publish_status === 'UNKNOWN' ? 'Publication result uncertain' : 'Publication failed'} ({patch.publish_error}). Check GitHub access and remote PR state before retrying.</p>}
                  {!patchReview && <button type="button" className="button button-white" onClick={() => void loadPatchReview(patch.id).catch((cause) => setError(cause instanceof Error ? cause.message : 'Patch review is unavailable.'))}>Load reviewed diff</button>}
                  {patchReview && <>
                    <div className="review-summary"><strong>{patch.files_changed ?? patchReview.changes.length} changed files</strong><span>+{patch.total_additions ?? '—'} / −{patch.total_deletions ?? '—'}</span></div>
                    <p className="review-context">Base commit <code>{patchReview.base_commit_sha || patch.base_commit_sha || 'Unavailable'}</code><br />Review digest <code>{patchReview.review_digest}</code></p>
                    <div className="review-workspace"><nav className="review-files" aria-label="Changed files">{patchReview.changes.map((change) => <button type="button" key={change.path} className={selectedChange?.path === change.path ? 'is-active' : ''} onClick={() => setSelectedDiffPath(change.path)} aria-current={selectedChange?.path === change.path ? 'true' : undefined}>{change.path}</button>)}</nav><div className="review-file-content"><h3>{selectedChange?.path || 'Select a changed file'}</h3>{selectedChange && <DiffFile diff={selectedChange.diff} />}</div></div>
                  </>}
                  {patch.status === 'GENERATED' && patchReview && (
                    <button type="button" className="button button-primary" disabled={patchBusy} onClick={approvePatch}>Approve this exact diff</button>
                  )}
                  {(patch.status === 'ACCEPTED' || patch.status === 'COMMITTED') && verification?.status === 'PASSED' && (
                    <button type="button" className="button button-primary" disabled={patchBusy || patch.publish_status === 'QUEUED' || patch.publish_status === 'RUNNING'} onClick={publishPatch}>
                      Publish dedicated branch and open pull request
                    </button>
                  )}
                  {patch.pull_request_url && <a href={patch.pull_request_url} target="_blank" rel="noopener noreferrer">Open GitHub pull request ↗</a>}
                </article>
              )}
            </div>
          </section>
        )}
      </main>
    </AppShell>
  );
}
