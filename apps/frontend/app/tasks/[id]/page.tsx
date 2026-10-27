'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Check, LoaderCircle, Play } from 'lucide-react';

import { env } from '../../../config/env';
import { AppShell } from '../../components/AppShell';

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

type ActiveTab = 'plan' | 'execution';

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

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [mutations, setMutations] = useState<Mutation[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>('plan');
  const [error, setError] = useState('');

  const authHeaders = useCallback(() => {
    const token = localStorage.getItem('forge_token');
    const orgId = localStorage.getItem('forge_org_id');

    return {
      Authorization: `Bearer ${token}`,
      'X-Organization-Id': orgId || '',
    };
  }, []);

  const fetchPlan = useCallback(async () => {
    try {
      const response = await fetch(
        `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans/${id}`,
        { headers: authHeaders() },
      );

      if (!response.ok) throw new Error('The plan could not be loaded.');
      setPlan(await response.json());
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
            `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${jobId}`,
            { headers: authHeaders() },
          ),
          fetch(
            `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${jobId}/logs`,
            { headers: authHeaders() },
          ),
        ]);

        if (jobResponse.ok) {
          const job = await jobResponse.json();
          setExecutionStatus(job.status);

          if (job.status === 'COMPLETED' || job.status === 'FAILED') {
            setExecuting(false);

            const mutationResponse = await fetch(
              `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/${jobId}/mutations`,
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
            logPayload.map((entry: { message: string }) => entry.message),
          );
        }
      } catch {
        setExecuting(false);
        setExecutionStatus('FAILED');
        setError('The execution stream was interrupted.');
      }
    },
    [authHeaders],
  );

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  useEffect(() => {
    if (!executionId || !executing) return;

    fetchExecution(executionId);
    
    const wsUrl = `${env.NEXT_PUBLIC_EVENT_URL}/api/v1/executions/${executionId}/ws`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data && data.message) {
          setLogs((prev) => {
            // Avoid duplicates
            if (prev[prev.length - 1] === data.message) return prev;
            return [...prev, data.message];
          });
          
          if (
            data.message === 'Execution completed successfully.' || 
            data.message.includes('Triggered Repository Memory') ||
            data.message.includes('Warning: Failed to trigger Memory') ||
            data.message.includes('Execution timed out') || 
            data.message.includes('Command failed')
          ) {
            // Fetch one last time to get mutations and final status
            // Wait 2s to ensure worker has committed the transaction
            setTimeout(() => fetchExecution(executionId), 2000);
          }
        }
      } catch (e) {
        console.error('Error parsing websocket message', e);
      }
    };

    return () => {
      ws.close();
    };
  }, [executionId, executing, fetchExecution]);

  const handleApprove = async () => {
    setApproving(true);
    setError('');

    try {
      const response = await fetch(
        `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/plans/${id}/approve`,
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
    setLogs(['Starting the isolated execution engine...']);
    setMutations([]);
    setError('');
    setActiveTab('execution');

    try {
      const response = await fetch(
        `${env.NEXT_PUBLIC_API_BASE_URL}/api/v1/executions/plans/${id}`,
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
      setExecutionStatus('FAILED');
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Forge could not start this execution.',
      );
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
  const canExecute = plan.status === 'APPROVED' && executionStatus === null;

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

        <nav className="segment-nav plan-segment-nav" aria-label="Plan views">
          <button
            type="button"
            className={activeTab === 'plan' ? 'is-active' : ''}
            onClick={() => setActiveTab('plan')}
          >
            <span>01</span>
            Plan architecture
          </button>
          <button
            type="button"
            className={activeTab === 'execution' ? 'is-active' : ''}
            onClick={() => setActiveTab('execution')}
          >
            <span>02</span>
            Execution stream
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
        ) : (
          <>
            <section className="execution-console">
              <header>
                <div>
                  <i />
                  <i />
                  <i />
                  <span>Forge terminal // isolated execution</span>
                </div>
                <strong>{executionStatus || 'Awaiting launch'}</strong>
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
                  <p>
                    No execution has started. Approve the action graph, then launch
                    it from the plan architecture view.
                  </p>
                )}

                {executing && (
                  <div className="terminal-pulse">
                    <span>--</span>
                    <code>Processing next verified action...</code>
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
              </footer>
            </section>

            {executionStatus === 'COMPLETED' && (
              <section className="mutation-section">
                <div className="mutation-heading">
                  <div className="eyebrow">
                    <span />
                    Applied mutations
                  </div>
                  <h2>Verified changes, file by file.</h2>
                  <p>
                    The execution finished successfully. Review the exact mutations
                    produced by the approved plan.
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
        )}
      </main>
    </AppShell>
  );
}
