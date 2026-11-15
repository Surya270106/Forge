'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

type FlightEvent = {
  id: string; execution_id: string; sequence: number; attempt: number;
  event_type: string; occurred_at: string; actor_type: string; actor_id: string | null; source: string;
  summary: string; data: Record<string, string | number | boolean>;
};
type TimelinePage = { events: FlightEvent[]; next_cursor: number | null };

export function FlightRecorder({ executionId, active, revision, authHeaders }: {
  executionId: string; active: boolean; revision: string; authHeaders: () => Record<string, string>;
}) {
  const [events, setEvents] = useState<FlightEvent[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [eventType, setEventType] = useState('');
  const [knownTypes, setKnownTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const lastSequence = useRef(0);
  const previousRevision = useRef(revision);

  const load = useCallback(async (after: number, replace = false, refresh = false) => {
    setLoading(true);
    try {
      const filter = eventType ? `&event_type=${encodeURIComponent(eventType)}` : '';
      const response = await fetch(`/api/v1/executions/${executionId}/timeline?cursor=${after}&limit=50${filter}`, { headers: authHeaders() });
      if (response.status === 401) { window.location.assign('/login'); return; }
      if (!response.ok) throw new Error('Execution history is unavailable.');
      const page: TimelinePage = await response.json();
      setKnownTypes((previous) => [...new Set([...previous, ...page.events.map((event) => event.event_type)])].sort());
      setEvents((previous) => {
        const known = new Map((replace ? [] : previous).map((event) => [event.id, event]));
        for (const event of page.events) known.set(event.id, event);
        const ordered = [...known.values()].sort((left, right) => left.sequence - right.sequence);
        lastSequence.current = ordered.at(-1)?.sequence || 0;
        return ordered;
      });
      if (!refresh) setCursor(page.next_cursor);
      setError('');
    } catch {
      setError('Execution history could not be loaded. Try again.');
    } finally {
      setLoading(false);
    }
  }, [authHeaders, eventType, executionId]);

  useEffect(() => { void load(0, true); }, [load]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void load(lastSequence.current, false, true), 5000);
    return () => window.clearInterval(timer);
  }, [active, load]);
  useEffect(() => {
    if (previousRevision.current !== revision) {
      previousRevision.current = revision;
      void load(lastSequence.current, false, true);
    }
  }, [revision, load]);

  const exportJson = async () => {
    try {
      const response = await fetch(`/api/v1/executions/${executionId}/timeline/export`, { headers: authHeaders() });
      if (response.status === 401) { window.location.assign('/login'); return; }
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `forge-execution-${executionId}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch { setError('Flight Recorder export failed. Try again.'); }
  };

  return <section className="flight-recorder" aria-label="Flight Recorder">
    <header>
      <div><span className="eyebrow">Flight Recorder</span><h2>Execution history</h2></div>
      <button type="button" onClick={() => void exportJson()}>Export JSON</button>
    </header>
    <label>Event type <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
      <option value="">All events</option>
      {knownTypes.map((type) => <option key={type} value={type}>{type}</option>)}
    </select></label>
    {error && <p role="alert">{error} <button type="button" onClick={() => void load(cursor || 0)}>Retry</button></p>}
    {!events.length && <p>{loading ? 'Loading execution history…' : 'No recorded events yet.'}</p>}
    <ol>
      {events.map((event) => <li key={event.id} data-category={event.event_type.split('.')[0]}
        className={event.event_type.endsWith('failed') ? 'is-failure' : event.event_type.includes('recovered') ? 'is-recovery' : ''}>
        <details>
          <summary><time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time>
            <strong>{event.summary}</strong><span>{event.actor_type} · attempt {event.attempt}</span></summary>
          <dl>
            <div><dt>Source</dt><dd>{event.source}</dd></div>
            {event.actor_id && <div><dt>Actor ID</dt><dd>{event.actor_id}</dd></div>}
            {Object.entries(event.data).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}
          </dl>
        </details>
      </li>)}
    </ol>
    {cursor !== null && <button type="button" disabled={loading} onClick={() => void load(cursor)}>{loading ? 'Loading…' : 'Load more events'}</button>}
  </section>;
}
