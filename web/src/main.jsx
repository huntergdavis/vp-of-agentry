import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { isNearBottom, shouldFollow } from './chat-scroll.js';
import { Message, MessageList } from '@chatscope/chat-ui-kit-react';
import '@chatscope/chat-ui-kit-styles/dist/default/styles.min.css';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import ReactMarkdown from 'react-markdown';
import TurndownService from 'turndown';
import './style.css';
import './dash.css';
import './scrollbars.css';
import { coverageEconomics, milestoneScenarios } from './coverage-economics.js';
import { CodewheelPicker } from './codewheel-picker.jsx';

const td = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });
const api = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('vp-auth-expired'));
    const detail = await response.json().catch(() => ({}));
    const error = new Error(detail.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response.json();
};

const DASH_ROUTES = {
  operations: { eyebrow: 'OPERATIONS', title: 'Operations', subtitle: 'Project progress, reproducibility, backlog and agents · one page, auto-calculated' },
  play: { eyebrow: 'LIVE GAME', title: 'Play Pool of Radiance', subtitle: 'Private DOS run · save states' },
  vp: { eyebrow: 'COMMAND CHANNEL', title: 'VP of Agentry', subtitle: 'The agent line' },
  agents: { eyebrow: 'AGENTS', title: 'Agents', subtitle: 'Talk to an agent directly' },
};

function useDashRoute() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const match = /^\/dash\/([a-z]+)\/?$/.exec(path);
  const hash = (window.location.hash || '').replace(/^#/, '');
  const fromHash = hash && hash in DASH_ROUTES ? hash : null;
  const view = match ? match[1] : (fromHash || Object.keys(DASH_ROUTES)[0]);
  return { standalone: path === '/dash' || path.startsWith('/dash/') || Boolean(fromHash),
           view, known: view in DASH_ROUTES };
}

function DashHeader({ eyebrow, title, subtitle, side, view, standalone }) {
  return <header className="dash-header">
    <div><span className="dash-eyebrow">{eyebrow}</span><h1>{title}</h1>{subtitle && <p className="dash-subtitle">{subtitle}</p>}</div>
    <div className="dash-side">
      {side}
      {view && !standalone && <a className="dash-link" href={`/#${view}`} title="Open this dashboard on its own route">Standalone ↗</a>}
    </div>
  </header>;
}

function DashNav({ view }) {
  return <nav className="dash-nav" aria-label="Dashboards">
    <span className="dash-nav-brand"><span className="dash-nav-mark">VA</span>VP OF AGENTRY</span>
    <span className="dash-nav-links">
      {Object.entries(DASH_ROUTES).map(([key, route]) => <a key={key} href={`/#${key}`} aria-current={view === key ? 'page' : undefined}>{route.title}</a>)}
    </span>
    <span className="dash-nav-right"><a className="dash-link" href="/">Open the desk ↗</a></span>
  </nav>;
}

function DashShell({ standalone, view, children }) {
  return <div className={`dash-root ${standalone ? 'dash-standalone' : 'dash-embedded'}`}>
    {standalone && <DashNav view={view} />}
    {children}
  </div>;
}

function Login({ onSuccess }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [next] = useState(() => new URLSearchParams(window.location.search).get('next') || '');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = await api('/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password, next }) });
      if (result.next) { window.location.assign(result.next); return; }
      onSuccess();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <main className="login-shell"><div className="login-card">
    <div className="brand-mark">VA</div><div className="eyebrow">PRIVATE EXECUTIVE DESK</div>
    <h1>VP of Agentry</h1><p>Live engineering direction, decisions, and delivery in one place.</p>
    <form onSubmit={submit}><label htmlFor="password">Owner password</label>
      <input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoFocus required />
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Open desk'}</button></form>
  </div></main>;
}

function Composer({ channel, onSend, pending, setPending, disabled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);
  const sendingRef = useRef(false);
  const sendRef = useRef(null);
  const editor = useEditor({ extensions: [StarterKit], content: '', editorProps: {
    attributes: { class: 'editor', 'aria-label': 'Message text' },
    handleKeyDown: (_view, event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        if (!event.repeat) sendRef.current?.();
        return true;
      }
      return false;
    },
  } });
  const command = (name) => { editor?.chain().focus()[name]().run(); };
  async function attach(files) {
    setError('');
    for (const file of Array.from(files).slice(0, 10 - pending.length)) {
      const form = new FormData(); form.append('file', file);
      try { const item = await api('/uploads', { method: 'POST', body: form }); setPending(items => [...items, item]); }
      catch (e) { setError(e.message); }
    }
  }
  async function send() {
    if (disabled || sendingRef.current) return;
    const body = td.turndown(editor?.getHTML() || '').trim();
    if (!body && !pending.length) return;
    sendingRef.current = true; setBusy(true); setError('');
    try {
      await onSend({ channel, body, attachment_ids: pending.map(a => a.id) });
      editor?.commands.clearContent(); setPending([]);
    } catch (e) { setError(e.message); } finally { sendingRef.current = false; setBusy(false); }
  }
  sendRef.current = send;
  return <section className="composer" aria-label="Write message">
    {pending.length > 0 && <div className="pending-files">{pending.map(file => <span key={file.id} className="file-pill">📎 {file.filename}<button aria-label={`Remove ${file.filename}`} onClick={() => setPending(items => items.filter(x => x.id !== file.id))}>×</button></span>)}</div>}
    <div className="toolbar" aria-label="Formatting">
      <button title="Bold" onClick={() => command('toggleBold')}><b>B</b></button><button title="Italic" onClick={() => command('toggleItalic')}><i>I</i></button>
      <button title="Heading" onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}>H</button>
      <button title="Bullet list" onClick={() => command('toggleBulletList')}>≡</button><button title="Quote" onClick={() => command('toggleBlockquote')}>❞</button>
      <button title="Code block" onClick={() => command('toggleCodeBlock')}>&lt;/&gt;</button>
      <span className="toolbar-spacer" /><button title="Attach images or files" onClick={() => fileRef.current?.click()}>＋ Attach</button>
      <input ref={fileRef} type="file" multiple hidden onChange={e => { attach(e.target.files); e.target.value = ''; }} />
    </div>
    <div onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); attach(e.dataTransfer.files); }}><EditorContent editor={editor} /></div>
    <div className="composer-footer"><span>{disabled ? 'Agent unavailable in Herdr' : 'Enter to send · Shift+Enter for a new line · files stay on this host'}</span>
      {error && <span className="form-error" role="alert">{error}</span>}
      <button className="primary send" disabled={busy || disabled} onClick={send}>{busy ? 'Sending…' : 'Send message ↗'}</button></div>
  </section>;
}

function MessageCard({ item, highlight, onSendNow, onInspect }) {
  const owner = item.role === 'owner';
  const [expanded, setExpanded] = useState(false);
  const long = String(item.body || '').length > 1200;
  const deliveryLabel = { inbox: 'delivered to inbox', read: 'read', acked: 'handled' }[item.delivery] || item.delivery;
  // Three visibly distinct owner-message states. 'acked' is transport, not an
  // answer: only answer_id (a link to the brief) counts as answered.
  const answerState = !owner ? null
    : item.answer_id ? 'answered'
    : ['acked', 'read'].includes(item.delivery) ? 'acknowledged'
    : 'unanswered';
  const answerLabel = { answered: 'answered', acknowledged: 'acknowledged · no reply yet', unanswered: 'unanswered' }[answerState];
  const waitingSeconds = Math.max(0, Math.floor((Date.now() - new Date(item.created_at).getTime()) / 1000));
  const waitingMinutes = Math.floor(waitingSeconds / 60);
  const heldForDraft = item.delivery_detail?.includes('someone is typing') || item.delivery_detail?.includes('input box contains a draft');
  return <div className={`message-wrap ${owner ? 'owner' : 'agent'} ${highlight ? 'highlight' : ''}`} id={`message-${item.id}`}>
    <div className="message-meta"><strong>{owner ? 'YOU' : 'AGENT'}</strong><span>{new Date(item.created_at).toLocaleString()}</span>{owner && <><span className={`delivery ${item.delivery}`} title={item.delivery_detail}>{deliveryLabel}</span><a className={`answer-state ${answerState}`} href={item.answer_id ? `#message-${item.answer_id}` : undefined} title={answerState === 'answered' ? `Answered by brief #${item.answer_id}` : answerState === 'acknowledged' ? 'Read/acknowledged, but no brief links this message yet' : 'Not read or answered yet'}>{answerLabel}</a></>}</div>
    <Message model={{ message: '', direction: owner ? 'outgoing' : 'incoming', position: 'single', sender: owner ? 'You' : 'Agent' }}>
      <Message.CustomContent><div className={`markdown ${long && !expanded ? 'clamped' : ''}`}><ReactMarkdown>{item.body}</ReactMarkdown></div>
        {long && <button className="message-expand" onClick={() => setExpanded(value => !value)}>{expanded ? 'Show less' : `Show full message (${String(item.body || '').length.toLocaleString()} chars)`}</button>}
        {item.attachments?.length > 0 && <div className="attachments">{item.attachments.map(a => <div key={a.id} className="attachment-card">{['image/png','image/jpeg','image/gif','image/webp'].includes(a.mime) && <a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer"><img src={`/api/uploads/${a.id}?preview=true`} loading="lazy" alt={a.filename} /></a>}<a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer">📎 {a.filename}</a></div>)}</div>}</Message.CustomContent>
    </Message>
    {owner && item.delivery === 'queued' && <div className={`queue-help ${heldForDraft && waitingMinutes >= 2 ? 'long-wait' : ''}`} role={heldForDraft && waitingMinutes >= 2 ? 'alert' : undefined}><span>{heldForDraft && waitingMinutes >= 2 ? 'Action needed: VP input box has an unfinished draft' : heldForDraft ? 'Waiting for the VP input box to clear' : (item.delivery_detail || 'Waiting for guarded delivery')} · {waitingMinutes < 1 ? 'under 1 min' : `${waitingMinutes} min`}</span>{heldForDraft && <button onClick={() => onSendNow(item)}>Send now</button>}</div>}
    {owner && item.delivery === 'inbox' && waitingSeconds >= 30 && <div className={`queue-help ${waitingMinutes >= 2 ? 'long-wait' : ''}`} role={waitingMinutes >= 2 ? 'alert' : undefined}><span>{item.delivery_detail || 'Stored in agent inbox'}; waiting for agent pickup · {waitingMinutes < 1 ? `${waitingSeconds} sec` : `${waitingMinutes} min`}</span></div>}
    {owner && item.delivery === 'failed' && <div className="queue-help"><span>{item.delivery_detail || 'Delivery failed; retrying when transport recovers'}</span></div>}
    {owner && item.delivery === 'uncertain' && <div className="queue-help"><span>Delivery uncertain. Check agent activity before resending.</span><button onClick={onInspect}>Live signal</button></div>}
  </div>;
}

function QuotaCard({ provider, quota }) {
  const name = provider === 'codex' ? 'CODEX' : 'CLAUDE';
  return <div>
    <b>{name} WEEKLY QUOTA</b>
    <strong>{quota ? quota.weekly_percent_left + '% left' : 'No reading'}</strong>
    <small>{quota
      ? `${quota.age_s > 3600 ? 'STALE · ' : ''}Observed ${Math.round(quota.age_s / 60)} min ago in ${quota.pane} · resets ${new Date(quota.reset_at).toLocaleString()} · other accounts unknown`
      : 'Awaiting a sourced quota update'}</small>
  </div>;
}

function CreditTrend({ events, current, ceiling, lastCreditAt }) {
  if (!events.length) return <div className="ops-credit-chart"><p>No verified credit events in the seven-day window.</p></div>;
  const begin = Date.parse(events[0].at), end = Date.now();
  const width = 760, left = 52, right = 738, top = 22, bottom = 177;
  const min = Math.max(0, Math.min(...events.map(row => row.value)) - 2);
  const max = Math.max(min + 1, current ?? 0, ...events.map(row => row.value));
  const x = at => left + (Date.parse(at) - begin) / Math.max(1, end - begin) * (right - left);
  const y = value => bottom - (value - min) / (max - min) * (bottom - top);
  const path = events.map((row, index) => `${index ? `H${x(row.at).toFixed(1)} V` : 'M' + x(row.at).toFixed(1) + ' '}${y(row.value).toFixed(1)}`).join(' ') + ` H${right}`;
  const recordedGain = events.at(-1).value - events[0].value;
  return <div className="ops-credit-chart">
    <div className="ops-credit-title"><div><span className="ops-kicker">VERIFIED CREDIT HISTORY</span><h3>Strict C functions · 7 days</h3></div><strong>{current ?? '—'} <small>/ {ceiling ?? '—'}</small></strong></div>
    <svg viewBox={`0 0 ${width} 215`} role="img" aria-label={`Step chart of ${events.length} verified strict C checkpoints; current ${current ?? 'unknown'} of ${ceiling ?? 'unknown'}`}>
      {[0, .5, 1].map(fraction => <g key={fraction}><path d={`M${left} ${y(min + (max - min) * fraction)} H${right}`} stroke="#35505d" strokeDasharray="3 5"/><text x="7" y={y(min + (max - min) * fraction) + 4}>{Math.round(min + (max - min) * fraction)}</text></g>)}
      <path d={path} fill="none" stroke="#a9db7d" strokeWidth="3" strokeLinejoin="round" />
      {events.map((row, index) => <circle key={`${row.at}-${index}`} cx={x(row.at)} cy={y(row.value)} r="4" fill="#d7efb8"><title>{new Date(row.at).toLocaleString()}: {row.value} reviewed functions</title></circle>)}
      <text x={left} y="204">{new Date(events[0].at).toLocaleDateString()}</text><text x={right} y="204" textAnchor="end">Now</text>
    </svg>
    <p>{recordedGain >= 0 ? '+' : ''}{recordedGain} net since the first visible checkpoint on {new Date(events[0].at).toLocaleDateString()}. Last new credit: {lastCreditAt ? new Date(lastCreditAt).toLocaleString() : 'unknown'}. The horizontal tail means no later credited change is recorded; it does not measure work in progress.</p>
  </div>;
}

function OwnerSnapshot() {
  const [snap, setSnap] = useState(null); const [error, setError] = useState('');
  const [board, setBoard] = useState(null);
  useEffect(() => { let alive = true; api('/ops-snapshot').then(d => alive && setSnap(d)).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, []);
  useEffect(() => { api('/ops-board').then(setBoard).catch(() => {}); }, []);
  const credit = board ? coverageEconomics(board.snapshot ?? board, board.history) : null;
  if (error) return <div className="snapshot-error" role="alert">Snapshot unavailable: {error}</div>;
  if (!snap) return <div className="muted">Loading snapshot…</div>;
  const num = c => c && c.value != null ? c.value : '—';
  const pct = p => p.denominator?.value ? Math.max(0, Math.min(100, 100 * (p.value?.value ?? 0) / p.denominator.value)) : 0;
  const latency = snap.reply_latency || {};
  const build = typeof __BUILD__ === 'object' ? __BUILD__ : {};
  return <div className="snapshot">
    <div className="snapshot-head"><div><div className="eyebrow">OWNER SNAPSHOT</div><h2>One page, auto-calculated</h2></div>
      <div className="snapshot-clock">oldest number <b>{snap.oldest_as_of ? new Date(snap.oldest_as_of).toLocaleString() : '—'}</b><small>reply p50 {latency.p50_s ?? '—'}s · p90 {latency.p90_s ?? '—'}s · max {latency.max_s ?? '—'}s · n {latency.n ?? '—'} · unanswered {latency.unanswered ?? '—'}</small></div></div>
    {snap.warnings?.length > 0 && <div className="snapshot-warn" role="alert">{snap.warnings.map((w, i) => <span key={i}>{w.source}: {w.reason}</span>)}</div>}
    <div className="snapshot-topline">
      <div className="snapshot-backlog-top">
        <h3>Backlog</h3>
        <div className="snapshot-backlog-counts">
          <span>{num(snap.backlog.open)} open</span><span>{num(snap.backlog.in_progress)} in progress</span><span>{num(snap.backlog.blocked)} blocked</span>
        </div>
        {snap.backlog.oldest_open && <div className="snapshot-backlog-oldest">oldest open <b>{snap.backlog.oldest_open.id}</b> · {(snap.backlog.oldest_open.age_s / 86400).toFixed(1)} d</div>}
        <div className="snapshot-held">held on owner decisions: <b>{snap.backlog.held?.count ?? '—'}</b>{snap.backlog.held?.oldest_days != null ? ` · oldest ${snap.backlog.held.oldest_days} d` : ''}</div>
      </div>
      <div className="snapshot-wiki">
        <h3>Wiki / context store</h3>
        <div className="snapshot-wiki-value">{num(snap.context?.articles)} articles</div>
        <small>{snap.context?.reason || 'unavailable'}</small>
      </div>
    </div>
    <div className="snapshot-projects">{snap.projects.map(p => <div className="snapshot-project" key={p.id}>
      <div className="snapshot-project-head"><b>{p.label}</b><span>{p.metric}</span></div>
      <div className="snapshot-bar"><i style={{ width: `${pct(p)}%` }} /></div>
      <div className="snapshot-value">{num(p.value)} <small>/ {num(p.denominator)} {p.denominator_label}</small></div>
      <div className="snapshot-truth">{p.truth}</div>
      {p.configuration && <div className="snapshot-config">{p.configuration}</div>}
      {p.value?.reason && <div className="snapshot-missing">— {p.value.reason}</div>}
    </div>)}</div>
    {credit && <div className="snapshot-credit"><h3>Verified credit history</h3><CreditTrend events={credit.events} current={credit.current} ceiling={credit.ceiling} lastCreditAt={credit.lastCreditAt} /></div>}
    {board?.quotas && <div className="snapshot-quotas"><h3>Provider windows</h3>
      <div className="snapshot-quota-row"><QuotaCard provider="codex" quota={board.quotas.codex} /><QuotaCard provider="claude" quota={board.quotas.claude} /></div>
    </div>}
    <div className="snapshot-activity">
      <h3>Agent activity · last 24h</h3>
      <div className="snapshot-table"><table><thead><tr><th>Agent</th><th>Messages</th><th>Median answer</th><th>Tasks done</th><th>Unread now</th></tr></thead>
        <tbody>{Object.entries(snap.agent_activity || {}).filter(([, v]) => v && typeof v === 'object' && !v.error).map(([pane, v]) => <tr key={pane}>
          <td>{pane}</td><td>{num(v.messages_24h)}</td>
          <td>{v.median_answer_s?.value != null ? `${v.median_answer_s.value}s` : <span title={v.median_answer_s?.reason || ''}>—</span>}</td>
          <td>{num(v.tasks_completed)}</td><td>{num(v.unread)}</td>
        </tr>)}{!Object.keys(snap.agent_activity || {}).length && <tr><td colSpan="5">No agent activity source.</td></tr>}</tbody></table></div>
    </div>
    <div className="snapshot-cols">
      <div><h3>Agents</h3><div className="snapshot-attribution"><b>attributed {snap.attribution?.attributed ?? '—'} PRs</b> <span>unattributed {snap.attribution?.unattributed ?? '—'} PRs</span><small>{snap.attribution?.method}</small></div><div className="snapshot-table"><table><thead><tr><th>Agent</th><th>Type</th><th>PRs</th><th>Bodies</th><th>Tasks</th><th>Msgs</th></tr></thead><tbody>{snap.agents.map(a => <tr key={a.agent}><td>{a.agent}</td><td>{a.type}</td><td>{num(a.merged_prs)}</td><td>{num(a.bodies_credited)}</td><td>{num(a.tasks_completed)}</td><td>{num(a.messages_handled)}</td></tr>)}{!snap.agents.length && <tr><td colSpan="6">No attributed agents yet.</td></tr>}</tbody></table></div><small>PRs carry their lane in the branch name from 2026-10-21.</small></div>
      <div><h3>Backlog · age is the number</h3><div className="snapshot-backlog"><span>{snap.backlog.open} open · {snap.backlog.in_progress} in progress · {snap.backlog.blocked} blocked</span>{snap.backlog.oldest_open && <b>oldest open {snap.backlog.oldest_open.id} · {(snap.backlog.oldest_open.age_s / 86400).toFixed(1)} d</b>}</div><ol>{snap.backlog.top.map(t => <li key={t.id}>{t.id} {t.title} <small>{t.priority} · {(t.age_s / 86400).toFixed(1)} d</small></li>)}</ol>{snap.backlog.reason && <div className="snapshot-missing">{snap.backlog.reason}</div>}</div>
      <div><h3>Context store</h3>{snap.context?.status === 'not_initialised' ? <div className="snapshot-missing">{snap.context.reason}</div> : null}</div>
    </div>
    <div className="snapshot-footer">build <b>{build.commit || 'unknown'}</b>{build.builtAt ? ` · ${new Date(build.builtAt).toLocaleString()}` : ''} · snapshot {snap.generated_at ? new Date(snap.generated_at).toLocaleString() : '—'} · oldest number {snap.oldest_as_of ? new Date(snap.oldest_as_of).toLocaleString() : '—'}</div>
  </div>;
}

function AgentList({ onSelect = () => {} }) {
  const [agents, setAgents] = useState(null); const [error, setError] = useState('');
  useEffect(() => { let alive = true; api('/agents').then(d => alive && setAgents(d.agents || [])).catch(e => alive && setError(e.message)); return () => { alive = false; }; }, []);
  if (error) return <div className="snapshot-error" role="alert">Agent registry unavailable: {error}</div>;
  if (!agents) return <div className="muted">Loading agents…</div>;
  if (!agents.length) return <div className="agent-empty"><b>No agents visible.</b><span>The pane registry returned no rows; nothing is assumed.</span></div>;
  return <div className="agent-list">
    <div className="agent-list-head"><div><div className="eyebrow">AGENTS</div><h2>Talk to an agent</h2></div><small>Status is what the tool reported; UNKNOWN is not inferred from a pane.</small></div>
    <div className="agent-rows">{agents.map(a => <div className={`agent-row ${a.status}`} key={a.id}>
      <div className="agent-id"><b>{a.name}</b><small>{a.pane_id || 'no live pane'}{a.cwd ? ` · ${a.cwd}` : ''}</small></div>
      <span className={`agent-status ${a.status}`} title={a.status_reason || ''}>{a.status.toUpperCase()}</span>
      <div className="agent-metrics">{a.metrics ? `${a.metrics.events} events` : 'no metrics'}{a.last_event ? <small>last event {new Date(a.last_event * 1000).toLocaleTimeString()}</small> : null}</div>
      {a.note ? <span className="agent-unavailable" title={a.note}>{a.note}</span> : a.pane_id ? <button className="agent-message" onClick={() => onSelect(a.id)}>Message</button> : <span className="agent-unavailable">{a.status_reason || 'unavailable'}</span>}
    </div>)}</div>
  </div>;
}

// DEAD: App renders StandaloneDesk, never this. Kept only until its nav,
// snapshot and agent-list pieces are confirmed live in the standalone path.
function VpStandalone() {
  const [channels, setChannels] = useState([]);
  const [items, setItems] = useState([]);
  const [pending, setPending] = useState([]);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const listRef = useRef(null);
  const nearBottomRef = useRef(true); const lastIdRef = useRef(null); const ownSendRef = useRef(null);
  const [showLatest, setShowLatest] = useState(false);
  const selected = channels.find(c => c.id === 'vp');
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [roster, messages] = await Promise.all([api('/channels'), api('/messages?channel=vp&limit=50')]);
        if (!live) return;
        setChannels(roster.channels || []);
        setItems(messages.items || []);
        setUpdated(new Date());
        setError('');
      } catch (e) { if (live) setError(e.message); }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => { live = false; clearInterval(timer); };
  }, []);
  useLayoutEffect(() => {
    const pane = listRef.current; if (!pane) return;
    const latest = items.at(-1)?.id ?? null;
    const previous = lastIdRef.current;
    lastIdRef.current = latest;
    const ownSend = ownSendRef.current != null && items.some(item => item.id === ownSendRef.current);
    const incoming = previous != null && latest != null && latest > previous;
    if (!incoming && !ownSend) return;
    if (incoming && !ownSend && !nearBottomRef.current) { setShowLatest(true); return; }
    nearBottomRef.current = true; setShowLatest(false);
    pane.scrollTop = pane.scrollHeight;
    if (ownSend) ownSendRef.current = null;
  }, [items]);
  function onScroll() {
    const pane = listRef.current; if (!pane) return;
    nearBottomRef.current = isNearBottom(pane);
    if (nearBottomRef.current) setShowLatest(false);
  }
  function jumpToLatest() {
    const pane = listRef.current; if (pane) pane.scrollTop = pane.scrollHeight;
    nearBottomRef.current = true; setShowLatest(false);
  }
  async function send(data) {
    const item = await api('/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: 'vp', ...data }) });
    ownSendRef.current = item.id;
    setItems(old => [...old, item]);
  }
  const route = DASH_ROUTES.vp;
  return <DashShell standalone view="vp">
    <DashHeader eyebrow={route.eyebrow} title={route.title} subtitle={route.subtitle} view="vp" standalone side={<>
      {selected && <span className="dash-meta">{selected.name} · {selected.status}</span>}
      <span className="dash-meta">updated {updated ? updated.toLocaleTimeString() : '—'}</span>
    </>} />
    <div className="dash-body dash-conversation">
      {error && <div className="dash-error" role="alert">{error}</div>}
      <div className="conversation" ref={listRef} onScroll={onScroll}>
        <div className="conversation-inner">
          {!items.length && <div className="empty-state"><div className="empty-icon">✦</div><h2>Direct line to {selected?.name || 'the agent'}</h2><p>Messages are delivered to the current Herdr agent. Agent briefs posted through the local API appear here.</p></div>}
          <MessageList>{items.map(item => <MessageCard key={item.id} item={item} onSendNow={() => {}} onInspect={() => {}} />)}</MessageList>
        </div>
      </div>
      {showLatest && <button className="jump-latest" onClick={jumpToLatest} aria-label="Jump to latest messages">New messages <span aria-hidden="true">↓</span></button>}
      <Composer channel="vp" onSend={send} pending={pending} setPending={setPending} disabled={!selected?.can_message} />
    </div>
  </DashShell>;
}

function StandaloneDesk({ view, known }) {
  if (!known) {
    return <DashShell standalone view={view}>
      <DashHeader eyebrow="DASHBOARDS" title="Unknown dashboard" subtitle={`No dashboard is registered at /dash/${view}`} />
      <div className="dash-body"><div className="dash-empty">Pick one of the four dashboards
        <div className="dash-nav-links" style={{ marginTop: 10 }}>{Object.entries(DASH_ROUTES).map(([key, route]) => <a key={key} href={`/#${key}`}>{route.title}</a>)}</div>
      </div></div>
    </DashShell>;
  }
  if (view === 'operations') return <OwnerSnapshot />;
  if (view === 'agents') return <AgentList onSelect={() => {}} />;
  if (view === 'play') return <PoolradPlay standalone />;
  return <VpStandalone />;
}

function RetiredNotice() {
  const [shell, setShell] = useState('');
  useEffect(() => { api('/herdr-webui').then(data => setShell(data.url || '')).catch(() => {}); }, []);
  const target = shell || `http://${window.location.hostname}:8789/`;
  return <div className="dash-root dash-standalone">
    <DashNav view="" />
    <DashHeader eyebrow="VP OF AGENTRY" title="The desk moved" subtitle="The Herdr web UI is the front door now" />
    <div className="dash-body">
      <div className="dash-empty">
        The old desk interface is retired. Terminals, workspaces and the four dashboards live in the Herdr web UI.
        <div style={{ marginTop: 12 }}><a className="dash-primary-link" href={target}>Open the Herdr web UI ↗</a></div>
        <div className="dash-nav-links" style={{ marginTop: 16 }}>
          {Object.entries(DASH_ROUTES).map(([key, route]) => <a key={key} href={`/#${key}`}>{route.title}</a>)}
        </div>
      </div>
    </div>
  </div>;
}

function BundleFingerprint() {
  const build = typeof __BUILD__ === 'object' ? __BUILD__ : { commit: 'unknown', builtAt: null };
  return <div className="page-fingerprint" title="Which build this page is">
    build <b>{build.commit}</b>{build.builtAt ? ` · ${new Date(build.builtAt).toLocaleString()}` : ''}
  </div>;
}

function App() {
  const route = useDashRoute();
  const [authorized, setAuthorized] = useState(null);
  useEffect(() => { api('/channels').then(() => setAuthorized(true)).catch(() => setAuthorized(false)); }, []);
  useEffect(() => { const expired = () => setAuthorized(false); window.addEventListener('vp-auth-expired', expired); return () => window.removeEventListener('vp-auth-expired', expired); }, []);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  useEffect(() => {
    const loadedVersion = document.querySelector('script[type="module"]')?.getAttribute('src');
    const check = () => api('/version').then(data => { if (loadedVersion && data.version !== loadedVersion) setUpdateAvailable(true); }).catch(() => {});
    const timer = setInterval(check, 15000); window.addEventListener('focus', check);
    return () => { clearInterval(timer); window.removeEventListener('focus', check); };
  }, []);
  if (authorized === null) return <div className="splash">VP OF AGENTRY</div>;
  const content = route.standalone
    ? (authorized ? <StandaloneDesk view={route.view} known={route.known} /> : <Login onSuccess={() => setAuthorized(true)} />)
    : (authorized ? <RetiredNotice /> : <Login onSuccess={() => setAuthorized(true)} />);
  return <>{updateAvailable && <div className="update-banner" role="status">A desk update is ready. Save any draft, then <button onClick={() => window.location.reload()}>Refresh now</button>.</div>}{content}<BundleFingerprint /></>;
}

createRoot(document.getElementById('root')).render(<App />);
