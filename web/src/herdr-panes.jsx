import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';

function PaneCard({ pane, focused, onFocus }) {
  const output = useRef(null);
  const following = useRef(true);
  useLayoutEffect(() => {
    if (following.current && output.current) output.current.scrollTop = output.current.scrollHeight;
  }, [pane.text, focused]);
  return <article className={`herdr-card ${focused ? 'focused' : ''}`} aria-label={`${pane.name} (${pane.pane_id})`}>
    <header><div><h2>{pane.name}</h2><p>{pane.workspace || 'Unlabelled workspace'} · {pane.pane_id} · {pane.agent || 'Terminal'}</p></div>
      <span className={`status-badge ${pane.status}`}>{pane.status}</span></header>
    <button className="herdr-focus" aria-pressed={focused} onClick={onFocus}>{focused ? 'Show all panes' : 'Focus pane'}</button>
    {pane.error && <p className="herdr-pane-error" role="status">{pane.error} · retrying</p>}
    <pre ref={output} tabIndex={0} aria-label={`Recent output for ${pane.pane_id}`} onScroll={() => {
      const node = output.current;
      following.current = node.scrollHeight - node.scrollTop - node.clientHeight < 40;
    }}>{pane.text || (pane.error ? 'Waiting for output…' : 'No recent output.')}</pre>
  </article>;
}

export function HerdrPanes({ api }) {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const [focused, setFocused] = useState(null);
  useEffect(() => {
    let stopped = false;
    let busy = false;
    let timer;
    const controller = new AbortController();
    async function refresh() {
      if (stopped || busy || document.hidden) return;
      clearTimeout(timer);
      busy = true;
      try {
        const data = await api('/panes/activity', { signal: controller.signal });
        if (!stopped) { setSnapshot(data); setError(''); }
      } catch (failure) {
        if (!stopped) setError(failure.message);
      } finally {
        busy = false;
        if (!stopped) timer = setTimeout(refresh, 4000);
      }
    }
    const visibility = () => { if (document.hidden) clearTimeout(timer); else refresh(); };
    refresh();
    document.addEventListener('visibilitychange', visibility);
    return () => { stopped = true; clearTimeout(timer); controller.abort(); document.removeEventListener('visibilitychange', visibility); };
  }, [api]);
  useEffect(() => {
    if (snapshot && !snapshot.panes.some(pane => pane.pane_id === focused)) setFocused(null);
  }, [snapshot, focused]);
  useEffect(() => {
    const escape = event => { if (event.key === 'Escape') setFocused(null); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, []);
  const panes = snapshot?.panes || [];
  return <section className="herdr-view" aria-label="Herdr panes">
    <div className="herdr-tools"><span>{snapshot ? `${panes.length} live panes` : 'Connecting to Herdr…'} · read-only · refreshes every 4 seconds</span>
      <span>{snapshot && `${error ? 'Last successful refresh' : 'Refreshed'} ${new Date(snapshot.checked_at).toLocaleTimeString()}`}</span></div>
    {error && <div className="herdr-error" role="alert">{error}. {snapshot ? 'Showing the last snapshot; it may be stale.' : 'Waiting for the first snapshot.'} Retrying automatically.</div>}
    {!snapshot && !error && <p className="herdr-empty" role="status">Loading live panes…</p>}
    {snapshot && !panes.length && <p className="herdr-empty" role="status">No live panes.</p>}
    <div className={`herdr-grid ${focused ? 'has-focus' : ''}`}>{panes.map(pane => <div key={pane.pane_id} hidden={Boolean(focused && pane.pane_id !== focused)}>
      <PaneCard pane={pane} focused={focused === pane.pane_id} onFocus={() => setFocused(current => current === pane.pane_id ? null : pane.pane_id)} />
    </div>)}</div>
  </section>;
}
