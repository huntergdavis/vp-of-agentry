import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Message, MessageList } from '@chatscope/chat-ui-kit-react';
import '@chatscope/chat-ui-kit-styles/dist/default/styles.min.css';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import ReactMarkdown from 'react-markdown';
import TurndownService from 'turndown';
import './style.css';
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

function Login({ onSuccess }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await api('/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) });
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

function PasswordSettings({ onClose }) {
  const [current, setCurrent] = useState(''); const [next, setNext] = useState(''); const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [saved, setSaved] = useState(false);
  async function submit(event) {
    event.preventDefault(); setError('');
    if (next !== confirm) { setError('New passwords do not match'); return; }
    setBusy(true);
    try { await api('/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: current, new_password: next }) });
      setCurrent(''); setNext(''); setConfirm(''); setSaved(true);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><div className="settings-modal" onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Change owner password">
    <div className="settings-head"><div><div className="eyebrow">OWNER ACCESS</div><h2>Change password</h2></div><button className="icon-button" onClick={onClose} aria-label="Close">×</button></div>
    <form onSubmit={submit}><label>Current password<input type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} required /></label>
      <label>New password<input type="password" autoComplete="new-password" minLength={12} value={next} onChange={e => setNext(e.target.value)} required /></label>
      <label>Confirm new password<input type="password" autoComplete="new-password" minLength={12} value={confirm} onChange={e => setConfirm(e.target.value)} required /></label>
      {error && <div className="form-error" role="alert">{error}</div>}{saved && <div className="settings-success" role="status">Password changed. Other browser sessions were signed out.</div>}
      <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save password'}</button></form>
  </div></div>;
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
  const deliveryLabel = { inbox: 'delivered to inbox', read: 'read', acked: 'handled' }[item.delivery] || item.delivery;
  const waitingSeconds = Math.max(0, Math.floor((Date.now() - new Date(item.created_at).getTime()) / 1000));
  const waitingMinutes = Math.floor(waitingSeconds / 60);
  const heldForDraft = item.delivery_detail?.includes('someone is typing') || item.delivery_detail?.includes('input box contains a draft');
  return <div className={`message-wrap ${owner ? 'owner' : 'agent'} ${highlight ? 'highlight' : ''}`} id={`message-${item.id}`}>
    <div className="message-meta"><strong>{owner ? 'YOU' : 'AGENT'}</strong><span>{new Date(item.created_at).toLocaleString()}</span>{owner && <span className={`delivery ${item.delivery}`} title={item.delivery_detail}>{deliveryLabel}</span>}</div>
    <Message model={{ message: '', direction: owner ? 'outgoing' : 'incoming', position: 'single', sender: owner ? 'You' : 'Agent' }}>
      <Message.CustomContent><div className="markdown"><ReactMarkdown>{item.body}</ReactMarkdown></div>
        {item.attachments?.length > 0 && <div className="attachments">{item.attachments.map(a => <div key={a.id} className="attachment-card">{['image/png','image/jpeg','image/gif','image/webp'].includes(a.mime) && <a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer"><img src={`/api/uploads/${a.id}?preview=true`} loading="lazy" alt={a.filename} /></a>}<a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer">📎 {a.filename}</a></div>)}</div>}</Message.CustomContent>
    </Message>
    {owner && item.delivery === 'queued' && <div className={`queue-help ${heldForDraft && waitingMinutes >= 2 ? 'long-wait' : ''}`} role={heldForDraft && waitingMinutes >= 2 ? 'alert' : undefined}><span>{heldForDraft && waitingMinutes >= 2 ? 'Action needed: VP input box has an unfinished draft' : heldForDraft ? 'Waiting for the VP input box to clear' : (item.delivery_detail || 'Waiting for guarded delivery')} · {waitingMinutes < 1 ? 'under 1 min' : `${waitingMinutes} min`}</span>{heldForDraft && <button onClick={() => onSendNow(item)}>Send now</button>}</div>}
    {owner && item.delivery === 'inbox' && waitingSeconds >= 30 && <div className={`queue-help ${waitingMinutes >= 2 ? 'long-wait' : ''}`} role={waitingMinutes >= 2 ? 'alert' : undefined}><span>{item.delivery_detail || 'Stored in agent inbox'}; waiting for agent pickup · {waitingMinutes < 1 ? `${waitingSeconds} sec` : `${waitingMinutes} min`}</span></div>}
    {owner && item.delivery === 'failed' && <div className="queue-help"><span>{item.delivery_detail || 'Delivery failed; retrying when transport recovers'}</span></div>}
    {owner && item.delivery === 'uncertain' && <div className="queue-help"><span>Delivery uncertain. Check agent activity before resending.</span><button onClick={onInspect}>Live signal</button></div>}
  </div>;
}

function ForceSendDialog({ item, busy, onClose, onConfirm }) {
  return <div className="modal-backdrop" onMouseDown={onClose}><div className="settings-modal" onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Send queued message now">
    <div className="settings-head"><div><div className="eyebrow">DELIVERY OVERRIDE</div><h2>Send this message now?</h2></div><button className="icon-button" onClick={onClose} aria-label="Close">×</button></div>
    <p className="override-copy">The VP pane appears to contain an unfinished draft. Sending now may combine your message with that draft. The queued copy will be cancelled first to prevent a duplicate.</p>
    <div className="override-actions"><button onClick={onClose} disabled={busy}>Keep waiting</button><button className="primary" onClick={() => onConfirm(item)} disabled={busy}>{busy ? 'Sending…' : 'Send now'}</button></div>
  </div></div>;
}

function Search({ onClose, onJump }) {
  const [q, setQ] = useState(''); const [results, setResults] = useState([]); const [busy, setBusy] = useState(false);
  const [nextBefore, setNextBefore] = useState(null); const [hasMore, setHasMore] = useState(false);
  useEffect(() => { if (q.trim().length < 2) { setResults([]); setHasMore(false); return; }
    let cancelled = false;
    const timer = setTimeout(async () => { setBusy(true); try { const data = await api(`/search?q=${encodeURIComponent(q.trim())}`); if (!cancelled) { setResults(data.items); setHasMore(data.has_more); setNextBefore(data.next_before); } } catch { if (!cancelled) setResults([]); } finally { if (!cancelled) setBusy(false); } }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q]);
  async function loadMore() {
    if (!hasMore || !nextBefore || busy) return;
    setBusy(true);
    try { const data = await api(`/search?q=${encodeURIComponent(q.trim())}&before=${nextBefore}`); setResults(old => [...old, ...data.items]); setHasMore(data.has_more); setNextBefore(data.next_before); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><div className="search-modal" onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Search conversation history">
    <div className="search-head"><input autoFocus placeholder="Search messages across projects…" value={q} onChange={e => setQ(e.target.value)} /><button onClick={onClose}>Esc ×</button></div>
    <div className="search-results">{busy && <div className="muted">Searching…</div>}{!busy && q.length >= 2 && !results.length && <div className="muted">No matching messages</div>}
      {results.map(item => <button key={item.id} className="search-result" onClick={() => { onJump(item); onClose(); }}><span>{item.channel.toUpperCase()} · {new Date(item.created_at).toLocaleString()}</span><strong>{item.body.slice(0, 260)}</strong></button>)}
      {hasMore && <button className="search-more" onClick={loadMore} disabled={busy}>{busy ? 'Loading…' : 'More results'}</button>}</div>
  </div></div>;
}

function LineTrend({ title, points, color, unit, note, step = false }) {
  const rows = points.filter(point => Number.isFinite(point.value) && Number.isFinite(Date.parse(point.at)));
  if (!rows.length) return <div className="ops-chart"><h3>{title}</h3><p className="muted">No observations in this window</p><small>{note}</small></div>;
  const first = Date.parse(rows[0].at), last = Date.parse(rows.at(-1).at);
  const high = Math.max(1, ...rows.map(row => row.value));
  const low = Math.min(0, ...rows.map(row => row.value));
  const x = row => 24 + (last === first ? 0.5 : (Date.parse(row.at) - first) / (last - first)) * 336;
  const y = row => 112 - ((row.value - low) / (high - low || 1)) * 92;
  const latest = rows.at(-1);
  return <div className="ops-chart"><div className="ops-chart-head"><h3>{title}</h3><strong>{latest.value} {unit}</strong></div>
    <svg viewBox="0 0 384 140" role="img" aria-label={`${title}: ${rows.length} timestamped observations, latest ${latest.value} ${unit}`}>
      <path d="M24 112 H360" stroke="#58717e" fill="none" />
      {step && rows.length > 1 && <path d={rows.map((row, index) => index ? `H${x(row)} V${y(row)}` : `M${x(row)} ${y(row)}`).join(' ')} fill="none" stroke={color} strokeWidth="3" />}
      {rows.map((row, index) => <circle key={`${row.at}-${index}`} cx={x(row)} cy={y(row)} r="4" fill={color}><title>{new Date(row.at).toLocaleString()}: {row.value} {unit}</title></circle>)}
      <text x="24" y="135">{new Date(rows[0].at).toLocaleString()}</text><text x="360" y="135" textAnchor="end">{new Date(latest.at).toLocaleTimeString()}</text>
    </svg><small>{note}</small></div>;
}

function MergeTrend({ merges, start, end }) {
  const begin = Date.parse(start), finish = Date.parse(end);
  if (!Number.isFinite(begin) || !Number.isFinite(finish)) return null;
  const buckets = Array.from({ length: 12 }, () => 0);
  for (const merge of merges) {
    const time = Date.parse(merge.merged_at);
    if (time >= begin && time <= finish) buckets[Math.min(11, Math.floor((time - begin) / (finish - begin) * 12))]++;
  }
  const high = Math.max(1, ...buckets);
  return <div className="ops-chart"><div className="ops-chart-head"><h3>PR merges · 24 hours</h3><strong>{merges.length} merged</strong></div>
    <svg viewBox="0 0 384 140" role="img" aria-label={`${merges.length} tracked PR merges in twelve two-hour intervals`}>
      <path d="M24 112 H360" stroke="#58717e" fill="none" />
      {buckets.map((count, index) => <rect key={index} x={28 + index * 28} y={112 - count / high * 92} width="18" height={count / high * 92} fill="#eab46f"><title>Bucket {index + 1}: {count} merges</title></rect>)}
      <text x="24" y="135">{new Date(start).toLocaleTimeString()}</text><text x="360" y="135" textAnchor="end">Now</text>
    </svg><small>Recent visible PRs only. A merge is not a deployment or strict C credit.</small></div>;
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

function RecreationLab({ snapshot, history }) {
  const lab = snapshot.experiment_lab || {};
  const model = coverageEconomics(snapshot, history);
  const roster = Object.fromEntries((snapshot.pane_roster || []).map(pane => [pane.pane_id, pane]));
  const messages = lab.messages_by_pane || [];
  const trials = lab.trials || [];
  const efficiency = lab.efficiency_by_type_model || [];
  const closedTrials = efficiency.reduce((total, row) => total + (row.completed_trials || 0), 0);
  const acceptedInClosedTrials = efficiency.reduce((total, row) => total + (row.completed_accepted_bodies || 0), 0);
  const costedClosedTrials = trials.filter(row => row.ended_at && row.metered_usd != null);
  const sourcedTrialSpend = costedClosedTrials.length
    ? costedClosedTrials.reduce((total, row) => total + row.metered_usd, 0)
    : null;
  const costsSourced = efficiency.filter(row => row.completed_trials > 0)
    .every(row => row.metered_usd != null);
  const trialDecision = closedTrials === 0
    ? 'No completed model trials yet.'
    : acceptedInClosedTrials === 0
      ? `No model winner: ${closedTrials} closed trials, zero accepted bodies.`
      : !costsSourced
        ? `No cost winner: ${acceptedInClosedTrials} accepted bodies in closed trials, with incomplete usage costs.`
        : 'Observed accepted-body rates and costs are available below; compare completed trials before choosing a lane mix.';
  const maxMessages = Math.max(1, ...messages.map(row => row.inbox_deliveries + row.direct_sends));
  const unknown = value => value == null ? 'Unmeasured' : value;
  return <section className="ops-mission" aria-label="815 candidate C bodies and agent experiment lab">
    <div className="ops-mission-head"><div><span className="ops-kicker">PRIMARY PROJECT GOAL / ORIGINAL C BODIES</span><h2>Recreate all 815 candidate bodies</h2><p>815 is the PM-reviewed static ceiling for non-library original starts, not a proven exact game-function count. Count substantive C bodies by original address; tests, PRs and demo work are quality or activity signals.</p></div><strong>{model.current ?? '—'} <span>/ {model.ceiling ?? 815}</span></strong></div>
    <div className="ops-mission-cards">
      <div><b>PUBLISHED PM CREDIT</b><strong>{model.current ?? '—'}</strong><small>{model.remaining ?? '—'} candidate targets still uncredited. Reviewed main {snapshot.function_progress?.commit_oid?.slice(0, 8) || 'unavailable'}; accounting observed {model.accountingAgeMinutes == null ? 'at an unknown time' : `${model.accountingAgeMinutes} min ago`}{model.accountingFresh ? '' : ' (stale)'}. Ceiling: PM-reviewed census PR #819.</small></div>
      <div><b>NEW CREDIT / 24H</b><strong>{model.credits24h == null ? 'Unknown' : `+${model.credits24h}`}</strong><small>Comparable reviewed checkpoints and an accounting sample within 60 minutes. A local draft does not change this number.</small></div>
      <div><b>NEW BODY LEDGER</b><strong>{lab.authored_bodies ?? 0} <span>authored</span></strong><small>{lab.accepted_bodies ?? 0} independently accepted since tracking began; logged separately from published credit to avoid double counting.</small></div>
      <div><b>SOURCED TRIAL SPEND</b><strong>{sourcedTrialSpend == null ? 'Unmeasured' : `$${sourcedTrialSpend.toFixed(2)}`}</strong><small>{costedClosedTrials.length}/{closedTrials} closed trials have attributed usage costs. This is trial spend only; model efficiency per dollar needs accepted bodies and complete cost records.</small></div>
    </div>
    <div className="ops-mission-main"><CreditTrend events={model.events} current={model.current} ceiling={model.ceiling} lastCreditAt={model.lastCreditAt}/>
      <div className="ops-lab-panel"><span className="ops-kicker">NEXT PROOF POINT</span><h3>First newly accepted C body</h3><p>PM reviews an exact authored head for source completeness. Write its focused test after the body and run bounded parity when host capacity permits. Record author/model, elapsed time, review effort and sourced cost.</p><small>ETA: no measured accepted-body rate yet. The existing 82 credits do not establish a current completion pace.</small></div></div>
    <div className="ops-lab-grid"><div className="ops-lab-panel"><div className="ops-lab-head"><h3>Messages delivered per agent · 24h</h3><span>{snapshot.sources?.agent_messages || 'unavailable'}</span></div>
      <div className="ops-table-wrap"><table><thead><tr><th>Agent</th><th>Type</th><th>Inbox</th><th>Direct</th></tr></thead><tbody>{messages.slice(0, 20).map(row => <tr key={row.pane_id}><td title={row.pane_id}>{row.agent_name || roster[row.pane_id]?.agent_name || 'Unnamed agent'}{(row.lane_name || roster[row.pane_id]?.lane_name) && <small>{row.lane_name || roster[row.pane_id]?.lane_name}</small>}<div className="ops-message-bar"><i style={{width:`${(row.inbox_deliveries + row.direct_sends) / maxMessages * 100}%`}} /></div></td><td>{roster[row.pane_id]?.agent_kind || 'Unknown'}</td><td>{row.inbox_deliveries}</td><td>{row.direct_sends}</td></tr>)}{!messages.length && <tr><td colSpan="4">No sourced delivery events in this window.</td></tr>}</tbody></table></div>
      <small>{lab.message_definition || 'Waiting for the delivery-event source.'} Counts are stored in the private database with event IDs and timestamps.</small></div>
      <div className="ops-lab-panel"><div className="ops-lab-head"><h3>Model and reasoning trials</h3><span>{trials.length} recorded</span></div>
      <p><b>TRIAL DECISION:</b> {trialDecision}</p>
      <div className="ops-table-wrap"><table><thead><tr><th>Type / model</th><th>Effort</th><th>Bodies</th><th>Accepted/hr</th><th>$/accepted</th></tr></thead><tbody>{efficiency.map(row => <tr key={`${row.agent_type}-${row.model}-${row.reasoning_effort}`}><td>{row.agent_type}<small>{row.model} · {row.completed_trials}/{row.trials} trials closed</small></td><td>{row.reasoning_effort}</td><td>{row.authored_bodies} / {row.accepted_bodies}</td><td>{unknown(row.accepted_per_hour)}</td><td>{row.usd_per_accepted == null ? 'Unmeasured' : `$${row.usd_per_accepted.toFixed(2)}`}</td></tr>)}{!efficiency.length && <tr><td colSpan="5">No trial recorded yet. Opus/Sonnet and Codex reasoning comparisons are queued.</td></tr>}</tbody></table></div>
      <small>Body counts are distinct authored function outputs per trial / latest exact-head acceptances. Later repairs retain the earlier trial's authored output without assigning its acceptance. Rates use completed trial hours; review time and usage dollars appear only where sourced.</small>
      <details><summary>Individual trial records</summary><div className="ops-table-wrap"><table><thead><tr><th>Pane</th><th>Model / effort</th><th>Minutes</th><th>Messages</th><th>Review</th></tr></thead><tbody>{trials.map(row => <tr key={row.trial_id}><td>{row.pane_id}</td><td>{row.model}<small>{row.reasoning_effort || 'unspecified'}</small></td><td>{Math.round(row.elapsed_hours * 60)}</td><td>{row.inbox_deliveries} inbox / {row.direct_sends} direct</td><td>{row.correction_minutes == null ? 'Unmeasured' : `${row.correction_minutes} min`}</td></tr>)}</tbody></table></div></details>
      <small>Stored per trial: model, provider, reasoning effort, start/end, function IDs and status, review time, delivered messages, host PSI, tokens and measured cost when sourced.</small></div></div>
  </section>;
}

function CoverageEconomics({ snapshot, history }) {
  const [lanes, setLanes] = useState(6);
  const [weekly, setWeekly] = useState(10);
  const model = coverageEconomics(snapshot, history, { lanes, creditsPerWeek: weekly });
  const milestones = milestoneScenarios(model.current, model.ceiling, weekly);
  const laneGoal = snapshot.goals?.find(goal => goal.goal_key === 'strict_c_assigned_lanes');
  const compileGoal = snapshot.goals?.find(goal => goal.goal_key === 'strict_c_compile_slots');
  const money = value => value == null ? 'Unavailable' : '$' + value.toFixed(2);
  return <section className="ops-executive" aria-label="C coverage economics and outlook">
    <div className="ops-executive-head"><div><span className="ops-kicker">POOLRAD / EXECUTIVE OUTLOOK</span><h2>C coverage economics</h2><p>Measured credit, fixed commitment, and a changeable planning scenario.</p></div><span className="ops-evidence-pill">PM-REVIEWED CREDIT</span></div>
    <div className="ops-executive-cards">
      <div><span className="ops-kicker">CREDITED FUNCTIONS</span><strong>{model.current ?? '—'} <em>/ {model.ceiling ?? '—'}</em></strong><small>{model.remaining ?? '—'} remain to the working ceiling. This is source coverage, not playable progress.</small></div>
      <div><span className="ops-kicker">LAST 24 HOURS</span><strong>{model.credits24h == null ? 'Unknown' : `+${model.credits24h}`}</strong><small>{model.credits24h == null ? 'No comparable verified checkpoint.' : 'Net new PM-reviewed strict C functions; candidate work earns no credit.'}</small></div>
      <div><span className="ops-kicker">FIXED POOL / CALENDAR HOUR</span><strong>{model.fixedHourly == null ? 'Unknown' : money(model.fixedHourly) + '/hr'}</strong><small>{snapshot.monthly_fixed_usd == null ? 'Owner cost source unavailable.' : `${money(snapshot.monthly_fixed_usd)}/month ÷ ${snapshot.calendar_hours_in_month} calendar hours.`} Excludes metered usage.</small></div>
      <div className="ops-unavailable"><span className="ops-kicker">ACTUAL C SPEND / HOUR</span><strong>Unavailable</strong><small>No measured C lane-hours, provider billing allocation, or metered usage series. Quota percentages are not dollars.</small></div>
    </div>
    <div className="ops-capacity-line"><b>C STAFFING / EXECUTION</b><span>{laneGoal?.status === 'verified' && laneGoal.value != null ? `${laneGoal.value} assigned / ${laneGoal.target ?? 6} planned` : 'Current C assignments unverified'}{compileGoal?.value != null ? ` · ${compileGoal.value} compile/native slots authorized` : ''}{laneGoal?.observed_at ? ` · PM checkpoint ${new Date(laneGoal.observed_at).toLocaleString()}` : ''}. Assignment is not productive lane time; the six-lane cost control is a planning assumption.</span></div>
    {model.credits24h != null && model.fixedHourly != null && <div className="ops-signal-line"><b>24-HOUR SIGNAL</b><span>+{model.credits24h} new reviewed C functions while {money(model.fixedHourly * 24)} of known fixed subscriptions elapsed across all work. This is not C-attributed spend or evidence of productive lane-hours.</span></div>}
    <div className="ops-executive-body"><CreditTrend events={model.events} current={model.current} ceiling={model.ceiling} lastCreditAt={model.lastCreditAt} />
      <div className="ops-model"><span className="ops-kicker">PLANNING SCENARIO · NOT A FORECAST</span><h3>What would it take?</h3>
        <p>Assume the whole fixed subscription pool supports {lanes} C lanes every calendar hour, and {weekly} new functions pass review every week. Neither assumption is an observed work rate. Change either input to inspect the math.</p>
        <div className="ops-model-inputs"><label>Modeled C lanes<input type="number" min="1" max="20" value={lanes} onChange={event => setLanes(Math.max(1, Math.min(20, Number(event.target.value) || 1)))} /></label>
          <label>New verified functions / week<input type="number" min="1" max="500" value={weekly} onChange={event => setWeekly(Math.max(1, Math.min(500, Number(event.target.value) || 1)))} /></label></div>
        <div className="ops-model-result"><div><small>EQUAL POOL ALLOCATION</small><strong>{model.laneHourly == null ? 'Unknown' : money(model.laneHourly) + '/lane-hr'}</strong><span>Fixed calendar-hour pool ÷ {lanes} modeled lanes, all hours. This is not observed lane spend.</span></div>
          <div><small>TO WORKING CEILING</small><strong>{model.scenarioWeeks == null ? 'Unknown' : model.scenarioWeeks.toFixed(1) + ' weeks'}</strong><span>{model.remaining ?? '—'} remaining ÷ {weekly} newly credited per week. No evidence-backed ETA.</span></div></div>
        <p className="ops-rate-note">Required modeled pace: {(weekly / lanes).toFixed(2)} reviewed functions per lane-week if every modeled lane contributes equally.</p>
        <table className="ops-milestones"><thead><tr><th>Strict C milestone</th><th>More functions</th><th>Scenario weeks</th></tr></thead><tbody>{milestones.map(row => <tr key={row.share}><td>{Math.round(row.share * 100)}% · {row.target}/{model.ceiling}</td><td>+{row.additional}</td><td>{row.weeks.toFixed(1)}</td></tr>)}</tbody></table>
        <p className="ops-model-limit">At this assumed duration the fixed subscription commitment would be {money(model.scenarioCalendarCost)} if this month’s hourly rate held constant; this is not incremental C cost and excludes usage, taxes, and staffing. The working denominator can change with review.</p>
      </div></div>
    <div className="ops-next-evidence"><b>NEXT EVIDENCE GATES</b><span>Record verified strict C credit with timestamp and exact source head; measure C lane-hours and billable usage for actual spend; capture a same-run DOS/C frame for the playable demo. No defensible delivery date yet.</span></div>
  </section>;
}

function OpsSummary({ auto = true }) {
  const [snapshot, setSnapshot] = useState(null);
  const [history, setHistory] = useState(null);
  const [weekHistory, setWeekHistory] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true); setError('');
    try {
      setSnapshot(await api('/ops-metrics/refresh', { method: 'POST' }));
      const [day, week] = await Promise.all([api('/ops-metrics/history'), api('/ops-metrics/history?hours=168')]);
      setHistory(day); setWeekHistory(week);
    }
    catch (exc) { setError(exc.message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!auto) return undefined;
    let active = true;
    const load = () => Promise.all([api('/ops-metrics'), api('/ops-metrics/history'), api('/ops-metrics/history?hours=168')])
      .then(([data, timeline, week]) => { if (active) { setSnapshot(data); setHistory(timeline); setWeekHistory(week); setError(''); } })
      .catch(exc => { if (active) setError(exc.message); });
    load();
    const timer = setInterval(load, 60000);
    return () => { active = false; clearInterval(timer); };
  }, [auto]);
  const coderStates = snapshot?.staff?.coder || {};
  const coders = Object.values(coderStates).reduce((sum, count) => sum + count, 0);
  const progress = snapshot?.function_progress;
  const playable = snapshot?.goals?.find(goal => goal.goal_key === 'playable_c_demo');
  const quotas = snapshot?.quotas || {
    codex: snapshot?.quota?.provider === 'codex' ? snapshot.quota : null,
    claude: snapshot?.quota?.provider === 'claude' ? snapshot.quota : null,
  };
  const subscriptions = snapshot?.subscriptions || [];
  const opencodeUsage = snapshot?.opencode_usage;
  const hostHealth = snapshot?.host_health;
  const strictSeries = (history?.goal_observations || []).filter(row => row.goal_key === 'strict_fullc').map(row => ({ at: row.observed_at, value: Number(row.value) }));
  const identitySeries = (history?.goal_observations || []).filter(row => row.goal_key === 'verified_game_identities').map(row => ({ at: row.observed_at, value: Number(row.value) }));
  const coderSeries = (history?.coder_samples || []).map(row => ({ at: row.observed_at, value: row.working }));
  return <section className="dashboard-view ops-view" aria-label="Private operations dashboard">
    <div className="dashboard-tools"><span>Private sourced observations · scheduled sample every minute</span><button onClick={refresh} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh data'}</button></div>
    {error && <div className="dashboard-error" role="alert">{error} <button onClick={refresh}>Try again</button></div>}
    <div className="ops-metrics"><div className="ops-heading"><strong>OPERATIONS METRICS</strong><small>{snapshot?.latest_sample_at ? 'Sample ' + new Date(snapshot.latest_sample_at).toLocaleTimeString() : 'Loading…'}</small></div>
    {snapshot && weekHistory && <RecreationLab snapshot={snapshot} history={weekHistory} />}
    {snapshot && weekHistory && <details className="ops-reference"><summary>Reviewed credit history and fixed-cost planning reference</summary><CoverageEconomics snapshot={snapshot} history={weekHistory} /></details>}
    {progress && <p className="ops-source-line">Published main {progress.commit_oid.slice(0, 8)} · checkpoint {new Date(progress.observed_at).toLocaleString()} · {progress.verified_game_identities} verified identities / {progress.ceiling} working ceiling; identity is separate from strict C credit.</p>}
    {history && <><div className="ops-section-head"><h2>Engineering flow · last 24 hours</h2><small>Recorded events and observations; no values are inferred between samples.</small></div>
      <div className="ops-charts">
        <LineTrend title="Reviewed strict C" points={strictSeries} color="#a9db7d" unit="functions" step note="Dated verified credit events; no credit from PR count or candidate rows." />
        <MergeTrend merges={history.pr_merges} start={history.window_start} end={history.generated_at} />
        <LineTrend title="Working coder panes" points={coderSeries} color="#83c6ed" unit="panes" note="Sampled process presence, not verified productive work; missing samples are gaps." />
        <LineTrend title="Verified game identities" points={identitySeries} color="#d6a6e8" unit="identities" step note="Dated verified identity events; distinct from strict C credit." />
      </div><p className="ops-dora">DORA deployment frequency, change failure rate, and recovery time: unavailable until deployment and incident records exist. PR merges above measure review throughput.</p></>}
    {snapshot && <div className="ops-grid">
      <div><b>STAFFING</b><strong>{coders} tracked coder panes</strong><small>{Object.entries(coderStates).map(([state, count]) => state + ' ' + count).join(' · ') || 'No coder sample'}</small></div>
      <div><b>PLAYABLE GAME GATE</b><strong>{playable?.status || 'Unverified'}</strong><small>{playable?.observed_at ? `Last manual checkpoint ${new Date(playable.observed_at).toLocaleString()} · ` : ''}A same-state DOS/C full frame is still required; no whole-game completion percentage is available</small></div>
      <QuotaCard provider="codex" quota={quotas.codex} />
      <QuotaCard provider="claude" quota={quotas.claude} />
      <div><b>FIXED SUBSCRIPTIONS</b><strong>{snapshot.monthly_fixed_usd == null ? 'Unavailable' : '$' + snapshot.monthly_fixed_usd.toFixed(2) + '/mo'}</strong><small>{subscriptions.map(item => item.provider + ' $' + item.monthly_usd.toFixed(2) + '/mo').join(' · ') || 'No owner cost record'} · owner reported</small></div>
      <div><b>OPENCODE MODEL COST</b><strong>{opencodeUsage ? '$' + opencodeUsage.month_estimated_usd.toFixed(4) + ' this month' : 'Unavailable'}</strong><small>{opencodeUsage ? `All local sessions $${opencodeUsage.all_time_estimated_usd.toFixed(4)} · ${opencodeUsage.session_count} sessions · observed ${new Date(opencodeUsage.observed_at).toLocaleString()} · ${opencodeUsage.scope}` : 'Local OpenCode cost source unavailable'} · no metered billing source</small></div>
      <div><b>HOST HEALTH</b><strong>{hostHealth ? `${hostHealth.stale ? 'STALE · ' : ''}/tmp ${Math.round(hostHealth.tmp_used_fraction * 100)}% · ${hostHealth.levels.tmp || 'unknown'}` : 'Unavailable'}</strong><small>{hostHealth ? `${hostHealth.tmp_free_gib.toFixed(2)} GiB free · inodes ${Math.round(hostHealth.tmp_inode_used_fraction * 100)}% · load ${hostHealth.load1.toFixed(1)}/${hostHealth.load5.toFixed(1)} on ${hostHealth.cpus} CPUs · CPU pressure ${hostHealth.cpu_psi_some_avg60.toFixed(1)}% · ${hostHealth.process_count ?? '—'} processes, ${hostHealth.zombie_count ?? '—'} zombies · observed ${Math.round(hostHealth.age_s / 60)} min ago` : 'Host watcher has no saved sample'}</small></div>
    </div>}</div>
  </section>;
}

function HerdrWebUi() {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api('/herdr-webui').then(data => setConfig(data)).catch(e => setError(e.message));
  }, []);
  return <section className="dashboard-view herdr-webui-view" aria-label="Herdr web UI">
    <div className="dashboard-tools"><span>The live Herdr terminal UI runs as its own service; the desk only frames it.</span></div>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    {config && !config.available && <div className="dashboard-loading" role="status">The Herdr web UI is not configured on this host yet.</div>}
    {config?.available && <iframe title="Herdr web UI" src={config.url} allow="clipboard-read; clipboard-write" />}
  </section>;
}

function OpsBoard() {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [, setTick] = useState(0);

  async function load() {
    try { const data = await api('/ops-board'); setBoard(data); setError(''); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    const age = setInterval(() => setTick(value => value + 1), 1000);
    return () => { clearInterval(timer); clearInterval(age); };
  }, []);
  async function refresh() {
    setBusy(true);
    try { const data = await api('/ops-board/refresh', { method: 'POST' }); setBoard(data); setError(''); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const head = board?.headline || {};
  const boardAge = board?.generated_at
    ? Math.max(0, Math.round((Date.now() - Date.parse(board.generated_at)) / 1000))
    : null;
  const tasks = board?.tasks || {};
  const inbox = board?.inbox || {};
  const dunks = board?.dunks || {};
  const panes = board?.panes || {};
  const daemon = board?.daemon || {};
  const health = board?.health || {};
  const opsDb = board?.ops_db || {};
  const poolrad = board?.poolrad || {};
  const sources = board?.sources || {};
  const ago = seconds => {
    if (seconds == null) return 'age unknown';
    if (seconds < 90) return `${Math.max(0, Math.round(seconds))}s ago`;
    if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
    return `${(seconds / 3600).toFixed(1)}h ago`;
  };
  const share = value => value == null ? '—' : `${value}%`;
  const duration = seconds => {
    if (seconds == null) return 'unknown';
    if (seconds < 90) return `${Math.max(0, Math.round(seconds))}s`;
    if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };
  const unavailable = state => state !== 'ok';
  return <section className="dashboard-view ops-view" aria-label="Operations board">
    <div className="dashboard-tools"><span>Deterministic operations board · read from Dunking Sheep and the ops database · no model in the loop</span><button onClick={refresh} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh now'}</button></div>
    {error && <div className="dashboard-error" role="alert">{error} <button onClick={refresh}>Try again</button></div>}
    {board && <div className="ops-board">
      <div className="ops-board-head"><div><span className="ops-kicker">OPERATIONS BOARD</span><strong>Updated {ago(boardAge)}</strong></div>
        <div className="ops-sources">{Object.entries(sources).map(([name, state]) => <span key={name} className={`ops-source ${unavailable(state) ? 'bad' : ''}`}>{name}</span>)}</div></div>
      <div className="ops-stats">
        <div><b>STRICT C</b><strong>{share(head.strict_percent)}</strong><small>{head.strict_full_c ?? '—'} / {head.ceiling ?? 815} upper bound</small></div>
        <div><b>IDENTITIES</b><strong>{share(head.identity_percent)}</strong><small>{head.identities ?? '—'} / {head.ceiling ?? 815} upper bound</small></div>
        <div><b>TASK QUEUE</b><strong>{head.task_depth ?? '—'}</strong><small>{head.task_open ?? '—'} open · {head.task_in_progress ?? '—'} active · {head.task_blocked ?? '—'} blocked</small></div>
        <div><b>INBOX</b><strong>{head.inbox_unread ?? '—'}</strong><small>unread · oldest {ago(head.inbox_oldest_s)}</small></div>
        <div><b>DUNKS</b><strong>{head.dunks_running ?? '—'}/{head.dunks_total ?? '—'}</strong><small>schedules running</small></div>
        <div><b>AGENT PANES</b><strong>{head.panes_total ?? '—'}</strong><small>{head.panes_working ?? '—'} working</small></div>
        <div><b>HOST /TMP</b><strong>{head.tmp_used_fraction == null ? '—' : `${Math.round(head.tmp_used_fraction * 100)}%`}</strong><small>{head.tmp_free_gib == null ? 'host sample unavailable' : `${head.tmp_free_gib} GiB free · load ${(head.load1 ?? 0).toFixed(1)} on ${head.cpus ?? '—'} CPUs`}</small></div>
        <div><b>DAEMON</b><strong>{daemon.version ?? '—'}</strong><small>{daemon.herdr_available === false ? 'herdr unavailable' : `up ${duration(daemon.uptime_s)}`} · {daemon.queued_messages ?? 0} queued</small></div>
      </div>
      <div className="ops-board-grid">
        <div className="ops-panel"><div className="ops-panel-head"><h3>Task queue</h3><span>{tasks.depth ?? '—'} active</span></div>
          {tasks.state !== 'ok' ? <p className="ops-muted">Task queue unavailable ({tasks.error || 'unknown error'}).</p>
            : <div className="ops-table-wrap"><table><thead><tr><th>ID</th><th>Task</th><th>Status</th><th>Assignee</th><th>Age</th></tr></thead><tbody>
              {tasks.items.map(task => <tr key={task.id}><td>{task.id}</td><td>{task.title}<small>{task.priority} · {task.scope}{task.blocked_by?.length ? ` · blocked by ${task.blocked_by.join(', ')}` : ''}</small></td><td>{task.status}{task.lease_expires_in_s != null ? <small>lease in {duration(task.lease_expires_in_s)}</small> : null}</td><td>{task.assignees.join(', ') || '—'}</td><td>{ago(task.age_s)}</td></tr>)}
              {!tasks.items.length && <tr><td colSpan="5">No open tasks.</td></tr>}
            </tbody></table></div>}
          {tasks.by_assignee?.length ? <small>Load: {tasks.by_assignee.map(row => `${row.assignee} ${row.count}`).join(' · ')}</small> : null}
        </div>
        <div className="ops-panel"><div className="ops-panel-head"><h3>Agent inboxes</h3><span>{inbox.unread_total ?? '—'} unread</span></div>
          {inbox.state !== 'ok' ? <p className="ops-muted">Inbox statistics unavailable ({inbox.error || 'unknown error'}).</p>
            : <div className="ops-table-wrap"><table><thead><tr><th>Mailbox</th><th>Unread</th><th>Total</th><th>Oldest</th></tr></thead><tbody>
              {inbox.mailboxes.slice(0, 12).map(row => <tr key={row.mailbox}><td>{row.destination || row.mailbox}</td><td>{row.unread}</td><td>{row.total}</td><td>{row.unread ? ago(row.oldest_unread_s) : '—'}</td></tr>)}
            </tbody></table></div>}
        </div>
        <div className="ops-panel"><div className="ops-panel-head"><h3>Scheduled dunks</h3><span>{dunks.running ?? '—'}/{dunks.total ?? '—'} running</span></div>
          {dunks.state !== 'ok' ? <p className="ops-muted">Dunk schedule unavailable ({dunks.error || 'unknown error'}).</p>
            : <div className="ops-table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Target</th><th>Every</th><th>Next</th></tr></thead><tbody>
              {dunks.items.map(dunk => <tr key={dunk.id}><td>{dunk.id}</td><td>{dunk.name}<small>{dunk.status}{dunk.skip_count ? ` · ${dunk.skip_count} skipped` : ''}{dunk.last_error ? ` · ${dunk.last_error}` : ''}</small></td><td>{dunk.target_label || dunk.target}</td><td>{dunk.interval_minutes}m</td><td>{dunk.running && dunk.next_send_in_s != null ? `in ${Math.round(dunk.next_send_in_s / 60)}m` : 'stopped'}</td></tr>)}
              {!dunks.items.length && <tr><td colSpan="5">No schedules.</td></tr>}
            </tbody></table></div>}
        </div>
        <div className="ops-panel"><div className="ops-panel-head"><h3>Host and daemon health</h3><span>{health.state === 'ok' ? (health.ok ? 'healthy' : 'problems') : 'unavailable'}</span></div>
          <ul className="ops-health">
            <li><span>Daemon</span><strong>{daemon.version ?? '—'}</strong><small>{daemon.herdr_available ? 'herdr connected' : `herdr unavailable: ${daemon.herdr_hint || 'unknown'}`}</small></li>
            <li><span>Memory index</span><strong>{health.memory_chunks ?? '—'} chunks</strong><small>{health.memory_sources ?? '—'} sources · queue depth {health.queue_depth ?? '—'}</small></li>
            <li><span>Host sample</span><strong>{head.tmp_used_fraction == null ? 'unavailable' : `${Math.round(head.tmp_used_fraction * 100)}% /tmp`}</strong><small>{head.tmp_free_gib == null ? 'no saved sample' : `${head.tmp_free_gib} GiB free · inodes and CPU pressure in the reference view`}</small></li>
            <li><span>Published checkpoint</span><strong>{poolrad.commit_oid ? poolrad.commit_oid.slice(0, 8) : 'unavailable'}</strong><small>{poolrad.observed_at ? `observed ${ago(poolrad.age_s)}` : 'no reviewed accounting snapshot'}</small></li>
          </ul>
          {health.problems?.length ? <p className="ops-warn">Health problems: {health.problems.join('; ')}</p> : null}
        </div>
      </div>
      <details className="ops-reference" onToggle={event => setLegacyOpen(event.target.open)}><summary>Detailed reference: credit history, quotas, and cost planning</summary>
        {legacyOpen && <OpsSummary auto={legacyOpen} />}</details>
      <p className="ops-limits">{(board?.limits || []).join(' ')}</p>
    </div>}
  </section>;
}

function PoolradProgress() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load(force) {
    if (force) setBusy(true);
    try {
      const result = await api('/poolrad-dashboard/progress');
      setData(result); setError('');
    } catch (e) { if (force) setError(e.message); } finally { if (force) setBusy(false); }
  }
  useEffect(() => {
    load(false);
    const timer = setInterval(() => load(false), 60000);
    return () => clearInterval(timer);
  }, []);
  async function refresh() {
    setBusy(true); setError('');
    try { await api('/poolrad-dashboard/refresh', { method: 'POST' }); await load(false); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const share = value => value == null ? '—' : `${value}%`;
  const width = value => value == null ? 0 : Math.max(0, Math.min(100, value));
  const ready = data && data.status === 'reviewed' && data.ceiling;
  return <section className="dashboard-view poolrad-view" aria-label="Poolrad completion">
    <div className="dashboard-tools"><span>Completion against the PM-reviewed {data?.ceiling ?? 815} upper bound · published checkpoint</span><button onClick={refresh} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh snapshot'}</button></div>
    {error && <div className="dashboard-error" role="alert">{error} <button onClick={refresh}>Try again</button></div>}
    {!data && !error && <div className="dashboard-loading" role="status">Reading the published checkpoint…</div>}
    {data && <div className="poolrad-hero">
      <div className="poolrad-stat"><div className="num">{share(data.strict_percent)}</div><div className="label">STRICT C</div><div className="sub">{data.strict_full_c} / {data.ceiling ?? '—'} {String(data.bound_kind ?? '').replace('_', ' ')}</div><div className="track"><i style={{ width: `${width(data.strict_percent)}%` }} /></div></div>
      <div className="poolrad-stat"><div className="num">{share(data.identity_percent)}</div><div className="label">IDENTITIES</div><div className="sub">{data.identities} / {data.ceiling ?? '—'} {String(data.bound_kind ?? '').replace('_', ' ')}</div><div className="track"><i style={{ width: `${width(data.identity_percent)}%` }} /></div></div>
    </div>}
    {data && <p className="poolrad-evidence">{data.evidence_line}</p>}
    {data && <p className="poolrad-meta">generated {new Date(data.generated).toLocaleString()} · source {data.source} · commit {(data.commit || '').slice(0, 8) || '—'} · {ready ? `${data.remaining} candidate targets still uncredited` : 'reviewed checkpoint unavailable'}</p>}
  </section>;
}

function PoolradPlay({ vpChannel }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [stream, setStream] = useState(0);
  const [chat, setChat] = useState([]);
  const [draft, setDraft] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState('');
  const [code, setCode] = useState(() => { try { return localStorage.getItem('vp-codeword') || ''; } catch { return ''; } });
  const [states, setStates] = useState([]);
  const [saveTag, setSaveTag] = useState('');
  const [stateSlot, setStateSlot] = useState('');
  const [statesBusy, setStatesBusy] = useState(false);
  const [statesError, setStatesError] = useState('');
  const screenRef = useRef(null);
  const inputRevision = useRef(0), actionBusy = useRef(false);
  const chatLogRef = useRef(null);
  useEffect(() => {
    let live = true;
    const refresh = () => api('/game/status').then(data => { if (live) setStatus(data); }).catch(e => { if (live) setError(e.message); });
    refresh(); const timer = setInterval(refresh, 5000);
    return () => { live = false; clearInterval(timer); };
  }, []);
  useEffect(() => {
    if (!vpChannel) return;
    let live = true;
    const load = () => api(`/messages?channel=${encodeURIComponent(vpChannel.id)}&limit=15`)
      .then(data => { if (live) setChat(data.items || []); })
      .catch(e => { if (live) setChatError(e.message); });
    load(); const timer = setInterval(load, 4000);
    return () => { live = false; clearInterval(timer); };
  }, [vpChannel]);
  useEffect(() => { const pane = chatLogRef.current; if (pane) pane.scrollTop = pane.scrollHeight; }, [chat]);
  async function refreshStates() {
    try {
      const data = await api('/game/states');
      setStates(data.states || []);
      setStatesError('');
    } catch (e) { setStatesError(e.message); }
  }
  useEffect(() => { refreshStates(); }, [status?.run_name, status?.running]);
  async function saveState() {
    if (statesBusy) return;
    setStatesBusy(true); setStatesError('');
    try {
      await api('/game/savestate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag: saveTag.trim() }) });
      setSaveTag('');
      await refreshStates();
    } catch (e) { setStatesError(e.message); } finally { setStatesBusy(false); }
  }
  async function loadState() {
    if (statesBusy || !stateSlot) return;
    setStatesBusy(true); setStatesError('');
    try {
      await api('/game/loadstate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slot: Number(stateSlot) }) });
      setStream(n => n + 1);
    } catch (e) { setStatesError(e.message); } finally { setStatesBusy(false); }
  }
  async function autoCodeWord() {
    if (actionBusy.current) return { ok: false, error: 'Another game action is in progress.' };
    actionBusy.current = true; setBusy(true); setError('');
    try {
      const data = await api('/game/autocodeword', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      return { ok: true, ...data };
    } catch (e) { setError(e.message); return { ok: false, error: e.message }; }
    finally { actionBusy.current = false; setBusy(false); }
  }
  async function sendChat(text) {
    const body = (text ?? draft).trim();
    if (!body || !vpChannel) return;
    setChatBusy(true); setChatError('');
    try {
      await api('/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: vpChannel.id, body }) });
      setDraft('');
      const data = await api(`/messages?channel=${encodeURIComponent(vpChannel.id)}&limit=15`);
      setChat(data.items || []);
    } catch (e) { setChatError(e.message); } finally { setChatBusy(false); }
  }
  async function action(path, body) {
    if (actionBusy.current) return false;
    actionBusy.current = true; inputRevision.current++;
    setBusy(true); setError('');
    try {
      const data = await api(`/game/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
      if (typeof data.running === 'boolean') { setStatus(data); setStream(n => n + 1); }
      if (data.running) setTimeout(() => screenRef.current?.focus(), 100);
      return true;
    } catch (e) { setError(e.message); return false; }
    finally { actionBusy.current = false; setBusy(false); }
  }
  function keyDown(event) {
    if (actionBusy.current || !status?.running || event.ctrlKey || event.metaKey || event.altKey) return;
    const names = { ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', Enter: 'Return', ' ': 'space', Backspace: 'BackSpace', PageUp: 'Page_Up', PageDown: 'Page_Down' };
    const key = names[event.key] || (/^[a-z0-9]$/i.test(event.key) ? event.key.toLowerCase() : event.key);
    if (!/^(?:[a-z0-9]|F(?:[1-9]|1[0-2])|Up|Down|Left|Right|Return|Escape|space|BackSpace|Tab|Delete|Home|End|Page_Up|Page_Down)$/.test(key)) return;
    event.preventDefault();
    inputRevision.current++;
    api('/game/key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) }).catch(e => setError(e.message));
  }
  function sendText(submit) {
    const text = code.trim();
    if (!text) return;
    try { localStorage.setItem('vp-codeword', text); } catch {}
    action('type', { text, submit });
  }
  function sendWord(word) {
    setCode(word);
    try { localStorage.setItem('vp-codeword', word); } catch {}
    return action('type', { text: word, submit: true });
  }
  return <section className="game-view" aria-label="Play Poolrad">
    <div className="game-tools"><div><strong>Pool of Radiance</strong><small>{status?.running ? `Live private run · ${status.run_name}` : status?.run_name ? `Saved run · ${status.run_name}` : 'Ready for a new private run'}</small></div>
      <div className="game-actions">{!status?.running ? <><button onClick={() => action('start', { fresh: false })} disabled={busy}>{busy ? 'Starting…' : status?.run_name ? 'Resume saved run' : 'Start game'}</button>{status?.run_name && <button onClick={() => action('start', { fresh: true })} disabled={busy}>New run</button>}</> : <button onClick={() => action('stop')} disabled={busy}>Stop game</button>}</div></div>
    {error && <div className="game-error" role="alert">{error}</div>}
    <div className="game-stage" ref={screenRef} tabIndex={0} onKeyDown={keyDown} onClick={() => screenRef.current?.focus()} aria-label="Poolrad game screen; click here to control with keyboard">
      {status?.running ? <img key={stream} src={`/api/game/video?v=${stream}`} alt="Live Poolrad game display" draggable="false" /> : <div className="game-placeholder">Start the private DOS game to play here.</div>}
    </div>
    <div className="game-footer"><span>Click the screen, then use your keyboard. Arrow keys move; Enter selects; Escape goes back. Saves stay in the private run on this PC.</span>{status?.running && status.audio && <audio key={stream} controls preload="none" src={`/api/game/audio?v=${stream}`} aria-label="Poolrad game audio" />}</div>
    <div className="game-type">
      <label htmlFor="game-code">Type into game</label>
      <input id="game-code" value={code} onChange={e => setCode(e.target.value)} placeholder="Code word / text (press Enter to send)" onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); sendText(true); } }} aria-label="Text to type into the game" />
      <button onClick={() => sendText(true)} disabled={busy || !code.trim()}>Send + Enter</button>
      <button onClick={() => sendText(false)} disabled={busy || !code.trim()}>Send only</button>
      <button onClick={() => { setCode(''); try { localStorage.removeItem('vp-codeword'); } catch {} }} disabled={!code}>Clear</button>
    </div>
    <div className="game-saves" aria-label="Save states">
      <strong>Save states</strong>
      <input value={saveTag} onChange={e => setSaveTag(e.target.value)} placeholder="Tag this save (e.g. Sokal Keep first floor)" maxLength={80} aria-label="Save state tag" disabled={!status?.running || statesBusy} />
      <button onClick={saveState} disabled={!status?.running || statesBusy}>{statesBusy ? 'Working…' : 'Save state'}</button>
      <label>Quick load
        <select value={stateSlot} onChange={e => setStateSlot(e.target.value)} disabled={!status?.running || statesBusy || states.length === 0} aria-label="Save state to load">
          <option value="">{states.length ? 'Choose a save…' : 'No save states yet'}</option>
          {states.map(s => <option key={s.slot} value={s.slot}>{`${s.slot}. ${s.tag} — ${new Date(s.created).toLocaleString()}`}</option>)}
        </select>
      </label>
      <button onClick={loadState} disabled={!status?.running || statesBusy || !stateSlot}>Load state</button>
      {statesError && <span className="game-error" role="alert">{statesError}</span>}
    </div>
    <CodewheelPicker screenRef={screenRef} inputRevision={inputRevision} running={Boolean(status?.running)} runKey={status?.run_name} busy={busy} onSend={sendWord} onAuto={autoCodeWord} />
    <div className="game-chat" aria-label="Direct line to the VP">
      <div className="game-chat-head"><strong>Direct line to the VP</strong><small>Tell me where you are, what you want, or issue a quick action.</small></div>
      <div className="game-chat-log" ref={chatLogRef}>
        {chat.length === 0 && <div className="game-chat-empty">{vpChannel ? 'No messages yet. Say where you are, or hit Quicksave.' : 'VP channel unavailable.'}</div>}
        {chat.map(m => <div key={m.id} className={`game-chat-item ${m.role === 'owner' ? 'owner' : 'agent'}`}><span className="game-chat-role">{m.role === 'owner' ? 'You' : 'VP'}</span><span className="game-chat-body">{m.body}</span></div>)}
      </div>
      {chatError && <div className="game-error" role="alert">{chatError}</div>}
      <div className="game-chat-input">
        <textarea value={draft} onChange={e => setDraft(e.target.value)} placeholder="e.g. I am on Sokal Keep first floor, quicksave" rows={2} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }} aria-label="Message the VP" />
        <div className="game-chat-actions">
          <button className="primary send" onClick={() => sendChat()} disabled={chatBusy || !draft.trim() || !vpChannel}>{chatBusy ? 'Sending…' : 'Send to VP'}</button>
        </div>
      </div>
    </div>
  </section>;
}

function Desk({ onLogout }) {
  const [channels, setChannels] = useState([]); const [channel, setChannel] = useState('vp');
  const [dashboardView, setDashboardView] = useState(null);
  const dashboardOpen = dashboardView !== null;
  const [channelUpdated, setChannelUpdated] = useState(null);
  const [items, setItems] = useState([]); const [older, setOlder] = useState(false); const [loadingOlder, setLoadingOlder] = useState(false);
  const [pending, setPending] = useState([]); const [activity, setActivity] = useState(''); const [searchOpen, setSearchOpen] = useState(false); const [settingsOpen, setSettingsOpen] = useState(false); const [jumpId, setJumpId] = useState(null);
  const [forceTarget, setForceTarget] = useState(null); const [forceBusy, setForceBusy] = useState(false);
  const [activityStatus, setActivityStatus] = useState('connecting'); const [activityUpdated, setActivityUpdated] = useState(null); const [activityConnected, setActivityConnected] = useState(false); const [showActivity, setShowActivity] = useState(false);
  const [error, setError] = useState(''); const listRef = useRef(null); const sentinelRef = useRef(null); const cursorRef = useRef(null); const activityRef = useRef(null); const activityRequest = useRef(0); const itemsRef = useRef([]); const scrollToSentRef = useRef(null);
  const [showLatest, setShowLatest] = useState(false); const nearBottomRef = useRef(true); const lastMessageIdRef = useRef(null);
  const selected = channels.find(c => c.id === channel);
  const dashboardChannel = channels.find(c => c.dashboard);
  useEffect(() => { itemsRef.current = items; }, [items]);
  useLayoutEffect(() => {
    if (dashboardOpen) return;
    const latestId = items.at(-1)?.id ?? null;
    const previousId = lastMessageIdRef.current;
    lastMessageIdRef.current = latestId;
    const wanted = scrollToSentRef.current;
    const ownSend = wanted && items.some(item => item.id === wanted);
    const incoming = jumpId == null && previousId != null && latestId != null && latestId > previousId;
    if (!listRef.current || (!ownSend && !incoming)) return;
    if (incoming && !ownSend && !nearBottomRef.current) { setShowLatest(true); return; }
    const pane = listRef.current;
    const follow = () => { if (ownSend || nearBottomRef.current) pane.scrollTop = pane.scrollHeight; };
    nearBottomRef.current = true;
    setShowLatest(false);
    follow();
    const frame = requestAnimationFrame(() => requestAnimationFrame(follow));
    const observer = new ResizeObserver(follow);
    observer.observe(pane.querySelector('.conversation-inner'));
    const finish = setTimeout(() => { observer.disconnect(); if (ownSend) scrollToSentRef.current = null; }, 1800);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); clearTimeout(finish); };
  }, [items, jumpId, dashboardOpen]);
  function onConversationScroll() {
    const pane = listRef.current;
    if (!pane) return;
    nearBottomRef.current = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 80;
    if (nearBottomRef.current) setShowLatest(false);
  }
  function jumpToLatest() {
    if (jumpId != null) { setJumpId(null); return; }
    const pane = listRef.current;
    if (pane) pane.scrollTop = pane.scrollHeight;
    nearBottomRef.current = true;
    setShowLatest(false);
  }
  async function refreshChannels() { try { const data = await api('/channels'); setChannels(data.channels); setChannelUpdated(new Date(data.checked_at)); } catch (e) { setError(e.message); } }
  async function refreshMessages(reset = false) {
    try {
      const data = await api(`/messages?channel=${channel}&limit=50`);
      if (reset) { setItems(data.items); setOlder(data.has_more); cursorRef.current = data.next_before; requestAnimationFrame(() => requestAnimationFrame(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight; })); }
      else setItems(old => { const byId = new Map(old.map(item => [item.id, item])); for (const item of data.items) byId.set(item.id, item); return [...byId.values()].sort((a, b) => a.id - b.id); });
      const queued = itemsRef.current.filter(item => item.role === 'owner' && ['queued', 'inbox', 'read'].includes(item.delivery)).slice(0, 100);
      if (queued.length) {
        const states = await api(`/deliveries?channel=${channel}&ids=${queued.map(item => item.id).join(',')}`);
        setItems(old => old.map(item => states.deliveries[item.id] ? { ...item, ...states.deliveries[item.id] } : item));
      }
    } catch (e) { setError(e.message); }
  }
  async function loadOlder() {
    if (loadingOlder || !older || !cursorRef.current) return;
    setLoadingOlder(true);
    try { const oldHeight = listRef.current?.scrollHeight || 0; const oldTop = listRef.current?.scrollTop || 0;
      const data = await api(`/messages?channel=${channel}&limit=50&before=${cursorRef.current}`);
      setItems(old => [...data.items, ...old]); setOlder(data.has_more); cursorRef.current = data.next_before;
      requestAnimationFrame(() => { if (listRef.current) listRef.current.scrollTop = oldTop + listRef.current.scrollHeight - oldHeight; });
    } catch (e) { setError(e.message); } finally { setLoadingOlder(false); }
  }
  async function refreshActivity() {
    const ticket = ++activityRequest.current;
    try {
      const data = await api(`/activity?channel=${channel}`);
      if (ticket !== activityRequest.current) return;
      const pane = activityRef.current;
      const follow = !pane || pane.scrollHeight - pane.scrollTop - pane.clientHeight < 80;
      setActivity(data.text || 'No recent output.');
      setActivityStatus(data.status || 'unknown'); setActivityUpdated(new Date()); setActivityConnected(true);
      if (follow) requestAnimationFrame(() => { if (activityRef.current) activityRef.current.scrollTop = activityRef.current.scrollHeight; });
    } catch {
      if (ticket === activityRequest.current) { setActivityConnected(false); setActivityStatus('disconnected'); }
    }
  }
  useEffect(() => { refreshChannels(); const timer = setInterval(refreshChannels, 12000); return () => clearInterval(timer); }, []);
  useEffect(() => { lastMessageIdRef.current = null; nearBottomRef.current = true; setShowLatest(false); setItems([]); setPending([]); setActivity(''); setActivityUpdated(null); setActivityStatus('connecting'); setActivityConnected(false);
    if (jumpId != null) {
      api(`/messages/${jumpId}/context`).then(data => { setItems(data.items); setOlder(data.has_more); cursorRef.current = data.next_before;
        requestAnimationFrame(() => document.getElementById(`message-${jumpId}`)?.scrollIntoView({ block: 'center' }));
      }).catch(e => setError(e.message));
    } else refreshMessages(true);
    refreshActivity();
    const timer = setInterval(() => { if (jumpId == null) refreshMessages(); refreshActivity(); }, 5000);
    return () => { clearInterval(timer); activityRequest.current++; };
  }, [channel, jumpId]);
  useEffect(() => { if (!sentinelRef.current) return; const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) loadOlder(); }, { root: listRef.current, rootMargin: '100px' }); observer.observe(sentinelRef.current); return () => observer.disconnect(); }, [older, loadingOlder, channel, dashboardOpen]);
  useEffect(() => { if (!dashboardOpen && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight; }, [dashboardOpen]);
  useEffect(() => { const handler = e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true); } if (e.key === 'Escape') setSearchOpen(false); }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler); }, []);
  async function send(data) { const item = await api('/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }); scrollToSentRef.current = item.id; if (jumpId != null) setJumpId(null); else setItems(old => [...old, item]); }
  async function confirmSendNow(item) { setForceBusy(true); setError(''); try { const updated = await api(`/messages/${item.id}/send-now`, { method: 'POST' }); setItems(old => old.map(current => current.id === updated.id ? updated : current)); setForceTarget(null); } catch (e) { setError(e.message); setForceTarget(null); } finally { setForceBusy(false); } }
  function selectChannel(id) { setDashboardView(null); setChannel(id); setJumpId(null); }
  function jumpTo(item) { setDashboardView(null); setChannel(item.channel); setJumpId(item.id); }
  return <div className={`shell ${dashboardOpen ? 'dashboard-mode' : ''}`}>
    <aside className="sidebar"><div className="identity"><div className="brand-mark small">VA</div><div><strong>VP OF AGENTRY</strong><span>Executive desk</span></div></div>
      <div className="sidebar-section">PROJECT VIEW · {new Set(channels.filter(c => c.online && c.workspace).map(c => c.workspace)).size} live spaces</div><button className={`channel dashboard-nav ${dashboardView === 'poolrad' ? 'selected' : ''}`} onClick={() => setDashboardView('poolrad')}><span aria-hidden="true">▦</span><span>Poolrad dashboard</span><small>evidence</small></button>
      <button className={`channel dashboard-nav ${dashboardView === 'ops' ? 'selected' : ''}`} onClick={() => setDashboardView('ops')}><span aria-hidden="true">▤</span><span>Operations dashboard</span><small>metrics</small></button>
      <button className={`channel dashboard-nav ${dashboardView === 'play' ? 'selected' : ''}`} onClick={() => setDashboardView('play')}><span aria-hidden="true">▶</span><span>Play Poolrad</span><small>live game</small></button>
      <button className={`channel dashboard-nav ${dashboardView === 'herdr' ? 'selected' : ''}`} onClick={() => setDashboardView('herdr')}><span aria-hidden="true">▦</span><span>Herdr web UI</span><small>live terminals</small></button>
      <div className="sidebar-section">ACTIVE WORK</div>{channels.filter(c => c.activity_group === 'active').map(c => <button key={c.id} className={`channel ${!dashboardOpen && channel === c.id ? 'selected' : ''}`} onClick={() => selectChannel(c.id)}><span className={`status-dot ${c.status}`}/><span>{c.name}</span><small title={c.workspace || ''}>{c.workspace || c.status}</small></button>)}
      <div className="sidebar-section">ON STANDBY</div>{channels.filter(c => c.activity_group !== 'active').map(c => <button key={c.id} className={`channel ${!dashboardOpen && channel === c.id ? 'selected' : ''}`} onClick={() => selectChannel(c.id)}><span className={`status-dot ${c.status}`}/><span>{c.name}</span><small title={c.workspace || ''}>{c.workspace || c.status}</small></button>)}
      <div className="sidebar-bottom"><button onClick={() => setSearchOpen(true)}>⌕ <span>Search all messages</span><kbd>⌘K</kbd></button><button onClick={() => setSettingsOpen(true)}>⚙ <span>Change password</span></button><button onClick={async () => { await api('/logout', { method: 'POST' }); onLogout(); }}>↪ <span>Sign out</span></button></div>
    </aside>
    <main className="center"><header className="topbar"><div><div className="eyebrow">{dashboardView === 'poolrad' ? 'PROJECT VIEW / POOLRAD' : dashboardView === 'ops' ? 'PROJECT VIEW / OPERATIONS' : dashboardView === 'play' ? 'PROJECT VIEW / LIVE GAME' : dashboardView === 'herdr' ? 'PROJECT VIEW / HERDR' : `COMMAND CHANNEL / ${selected?.kind?.toUpperCase() || 'ACTIVE'}`}</div><h1>{dashboardView === 'poolrad' ? 'Poolrad completion' : dashboardView === 'ops' ? 'Operations dashboard' : dashboardView === 'play' ? 'Play Pool of Radiance' : dashboardView === 'herdr' ? 'Herdr web UI' : selected?.name || 'VP of Agentry'}</h1></div><div className="topbar-right">{dashboardOpen ? <button className="message-cta" onClick={() => dashboardChannel && selectChannel(dashboardChannel.id)} disabled={!dashboardChannel}>{dashboardChannel?.name || 'Project'} chat</button> : <><div className="presence"><span className={`status-badge ${selected?.status}`}>{selected?.online ? selected.status : 'offline'}</span><small title="Agent presence, not project health">Agent presence · {channelUpdated ? channelUpdated.toLocaleTimeString() : 'checking'}</small></div><button className="message-cta" onClick={() => document.querySelector('.editor')?.focus()} disabled={!selected?.can_message}>Message agent</button><button className="activity-toggle" onClick={() => setShowActivity(true)}>Live signal</button></>}<button className="icon-button" onClick={() => setSearchOpen(true)} title="Search">⌕</button><button className="icon-button" onClick={() => setSettingsOpen(true)} title="Change password">⚙</button></div></header>
      {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
      {dashboardView === 'herdr' ? <HerdrWebUi /> : dashboardView === 'poolrad' ? <PoolradProgress /> : dashboardView === 'ops' ? <OpsBoard /> : dashboardView === 'play' ? <PoolradPlay vpChannel={channels.find(c => c.id === 'vp')} /> : <><div className="conversation-frame"><div className="conversation" ref={listRef} onScroll={onConversationScroll}><div className="conversation-inner">{jumpId != null && <div className="jump-banner">Showing search result <button onClick={() => setJumpId(null)}>Return to latest ↗</button></div>}<div ref={sentinelRef} className="older-marker">{older ? (loadingOlder ? 'Loading earlier messages…' : <button onClick={loadOlder}>Load earlier messages</button>) : 'Beginning of recorded history'}</div>
        {!items.length && <div className="empty-state"><div className="empty-icon">✦</div><h2>Direct line to {selected?.name}</h2><p>Messages are delivered to the current Herdr agent. Agent briefs posted through the local API appear here; the live pane is visible at right.</p></div>}
        <MessageList>{items.map(item => <MessageCard key={item.id} item={item} highlight={item.id === jumpId} onSendNow={setForceTarget} onInspect={() => setShowActivity(true)} />)}</MessageList>
      </div></div>{showLatest && <button className="jump-latest" onClick={jumpToLatest} aria-label="Jump to latest messages">New messages <span aria-hidden="true">↓</span></button>}</div>
      <Composer channel={channel} onSend={send} pending={pending} setPending={setPending} disabled={!selected?.can_message} /></>}
    </main>
    {!dashboardOpen && <aside className={`activity ${showActivity ? 'open' : ''}`}><div className="activity-head"><button className="close-activity" onClick={() => setShowActivity(false)} aria-label="Close live signal">×</button><div className="eyebrow">LIVE SIGNAL</div><h2>Agent activity</h2><p>Recent terminal output from the existing pane</p><div className="activity-live"><span className={`status-dot ${activityConnected ? 'working' : ''}`}/><strong>{activityConnected ? 'Connected' : 'Reconnecting'}</strong><span>· agent {activityStatus}</span><span>· {activityUpdated ? `refreshed ${activityUpdated.toLocaleTimeString()}` : 'waiting for first refresh'}</span></div></div><div className="activity-body" ref={activityRef}><pre>{activity || (activityConnected ? 'No recent output.' : 'Connecting to Herdr…')}</pre></div><div className="activity-foot">Recent terminal view · refreshes every 5 seconds. Agent presence is not project health; actual decisions are in posted briefs.</div></aside>}
    {searchOpen && <Search onClose={() => setSearchOpen(false)} onJump={jumpTo} />}
    {settingsOpen && <PasswordSettings onClose={() => setSettingsOpen(false)} />}
    {forceTarget && <ForceSendDialog item={forceTarget} busy={forceBusy} onClose={() => setForceTarget(null)} onConfirm={confirmSendNow} />}
  </div>;
}

function App() {
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
  return <>{updateAvailable && <div className="update-banner" role="status">A desk update is ready. Save any draft, then <button onClick={() => window.location.reload()}>Refresh now</button>.</div>}{authorized ? <Desk onLogout={() => setAuthorized(false)} /> : <Login onSuccess={() => setAuthorized(true)} />}</>;
}

createRoot(document.getElementById('root')).render(<App />);
