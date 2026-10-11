import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Message, MessageList } from '@chatscope/chat-ui-kit-react';
import '@chatscope/chat-ui-kit-styles/dist/default/styles.min.css';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import ReactMarkdown from 'react-markdown';
import TurndownService from 'turndown';
import './style.css';

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
  const waitingMinutes = Math.max(0, Math.floor((Date.now() - new Date(item.created_at).getTime()) / 60000));
  const heldForDraft = item.delivery_detail?.includes('someone is typing') || item.delivery_detail?.includes('input box contains a draft');
  return <div className={`message-wrap ${owner ? 'owner' : 'agent'} ${highlight ? 'highlight' : ''}`} id={`message-${item.id}`}>
    <div className="message-meta"><strong>{owner ? 'YOU' : 'AGENT'}</strong><span>{new Date(item.created_at).toLocaleString()}</span>{owner && <span className={`delivery ${item.delivery}`}>{item.delivery}</span>}</div>
    <Message model={{ message: '', direction: owner ? 'outgoing' : 'incoming', position: 'single', sender: owner ? 'You' : 'Agent' }}>
      <Message.CustomContent><div className="markdown"><ReactMarkdown>{item.body}</ReactMarkdown></div>
        {item.attachments?.length > 0 && <div className="attachments">{item.attachments.map(a => <div key={a.id} className="attachment-card">{['image/png','image/jpeg','image/gif','image/webp'].includes(a.mime) && <a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer"><img src={`/api/uploads/${a.id}?preview=true`} loading="lazy" alt={a.filename} /></a>}<a href={`/api/uploads/${a.id}`} target="_blank" rel="noreferrer">📎 {a.filename}</a></div>)}</div>}</Message.CustomContent>
    </Message>
    {owner && item.delivery === 'queued' && <div className={`queue-help ${heldForDraft && waitingMinutes >= 2 ? 'long-wait' : ''}`} role={heldForDraft && waitingMinutes >= 2 ? 'alert' : undefined}><span>{heldForDraft && waitingMinutes >= 2 ? 'Action needed: VP input box has an unfinished draft' : heldForDraft ? 'Waiting for the VP input box to clear' : (item.delivery_detail || 'Waiting for guarded delivery')} · {waitingMinutes < 1 ? 'under 1 min' : `${waitingMinutes} min`}</span>{heldForDraft && <button onClick={() => onSendNow(item)}>Send now</button>}</div>}
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

function Desk({ onLogout }) {
  const [channels, setChannels] = useState([]); const [channel, setChannel] = useState('vp');
  const [channelUpdated, setChannelUpdated] = useState(null);
  const [items, setItems] = useState([]); const [older, setOlder] = useState(false); const [loadingOlder, setLoadingOlder] = useState(false);
  const [pending, setPending] = useState([]); const [activity, setActivity] = useState(''); const [searchOpen, setSearchOpen] = useState(false); const [settingsOpen, setSettingsOpen] = useState(false); const [jumpId, setJumpId] = useState(null);
  const [forceTarget, setForceTarget] = useState(null); const [forceBusy, setForceBusy] = useState(false);
  const [activityStatus, setActivityStatus] = useState('connecting'); const [activityUpdated, setActivityUpdated] = useState(null); const [activityConnected, setActivityConnected] = useState(false); const [showActivity, setShowActivity] = useState(false);
  const [error, setError] = useState(''); const listRef = useRef(null); const sentinelRef = useRef(null); const cursorRef = useRef(null); const activityRef = useRef(null); const activityRequest = useRef(0); const itemsRef = useRef([]); const scrollToSentRef = useRef(null);
  const selected = channels.find(c => c.id === channel);
  useEffect(() => { itemsRef.current = items; }, [items]);
  useLayoutEffect(() => {
    const wanted = scrollToSentRef.current;
    if (!wanted || !items.some(item => item.id === wanted) || !listRef.current) return;
    const pane = listRef.current;
    const follow = () => { pane.scrollTop = pane.scrollHeight; };
    follow();
    const frame = requestAnimationFrame(() => requestAnimationFrame(follow));
    const observer = new ResizeObserver(follow);
    observer.observe(pane.querySelector('.conversation-inner'));
    const finish = setTimeout(() => { observer.disconnect(); scrollToSentRef.current = null; }, 1800);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); clearTimeout(finish); };
  }, [items]);
  async function refreshChannels() { try { const data = await api('/channels'); setChannels(data.channels); setChannelUpdated(new Date(data.checked_at)); } catch (e) { setError(e.message); } }
  async function refreshMessages(reset = false) {
    try {
      const data = await api(`/messages?channel=${channel}&limit=50`);
      if (reset) { setItems(data.items); setOlder(data.has_more); cursorRef.current = data.next_before; requestAnimationFrame(() => requestAnimationFrame(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight; })); }
      else setItems(old => { const byId = new Map(old.map(item => [item.id, item])); for (const item of data.items) byId.set(item.id, item); return [...byId.values()].sort((a, b) => a.id - b.id); });
      const queued = itemsRef.current.filter(item => item.role === 'owner' && item.delivery === 'queued').slice(0, 100);
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
  useEffect(() => { setItems([]); setPending([]); setActivity(''); setActivityUpdated(null); setActivityStatus('connecting'); setActivityConnected(false);
    if (jumpId != null) {
      api(`/messages/${jumpId}/context`).then(data => { setItems(data.items); setOlder(data.has_more); cursorRef.current = data.next_before;
        requestAnimationFrame(() => document.getElementById(`message-${jumpId}`)?.scrollIntoView({ block: 'center' }));
      }).catch(e => setError(e.message));
    } else refreshMessages(true);
    refreshActivity();
    const timer = setInterval(() => { if (jumpId == null) refreshMessages(); refreshActivity(); }, 5000);
    return () => { clearInterval(timer); activityRequest.current++; };
  }, [channel, jumpId]);
  useEffect(() => { if (!sentinelRef.current) return; const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) loadOlder(); }, { root: listRef.current, rootMargin: '100px' }); observer.observe(sentinelRef.current); return () => observer.disconnect(); }, [older, loadingOlder, channel]);
  useEffect(() => { const handler = e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true); } if (e.key === 'Escape') setSearchOpen(false); }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler); }, []);
  async function send(data) { const item = await api('/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }); scrollToSentRef.current = item.id; if (jumpId != null) setJumpId(null); else setItems(old => [...old, item]); }
  async function confirmSendNow(item) { setForceBusy(true); setError(''); try { const updated = await api(`/messages/${item.id}/send-now`, { method: 'POST' }); setItems(old => old.map(current => current.id === updated.id ? updated : current)); setForceTarget(null); } catch (e) { setError(e.message); setForceTarget(null); } finally { setForceBusy(false); } }
  function selectChannel(id) { setChannel(id); setJumpId(null); }
  function jumpTo(item) { setChannel(item.channel); setJumpId(item.id); }
  return <div className="shell">
    <aside className="sidebar"><div className="identity"><div className="brand-mark small">VA</div><div><strong>VP OF AGENTRY</strong><span>Executive desk</span></div></div>
      <div className="sidebar-section">ACTIVE WORK</div>{channels.filter(c => c.kind === 'active').map(c => <button key={c.id} className={`channel ${channel === c.id ? 'selected' : ''}`} onClick={() => selectChannel(c.id)}><span className={`status-dot ${c.status}`}/><span>{c.name}</span><small>{c.status}</small></button>)}
      <div className="sidebar-section">ON STANDBY</div>{channels.filter(c => c.kind !== 'active').map(c => <button key={c.id} className={`channel ${channel === c.id ? 'selected' : ''}`} onClick={() => selectChannel(c.id)}><span className={`status-dot ${c.status}`}/><span>{c.name}</span><small>{c.status}</small></button>)}
      <div className="sidebar-bottom"><button onClick={() => setSearchOpen(true)}>⌕ <span>Search all messages</span><kbd>⌘K</kbd></button><button onClick={() => setSettingsOpen(true)}>⚙ <span>Change password</span></button><button onClick={async () => { await api('/logout', { method: 'POST' }); onLogout(); }}>↪ <span>Sign out</span></button></div>
    </aside>
    <main className="center"><header className="topbar"><div><div className="eyebrow">COMMAND CHANNEL / {selected?.kind?.toUpperCase() || 'ACTIVE'}</div><h1>{selected?.name || 'VP of Agentry'}</h1></div><div className="topbar-right"><div className="presence"><span className={`status-badge ${selected?.status}`}>{selected?.online ? selected.status : 'offline'}</span><small title="Agent presence, not project health">Agent presence · {channelUpdated ? channelUpdated.toLocaleTimeString() : 'checking'}</small></div><button className="message-cta" onClick={() => document.querySelector('.editor')?.focus()} disabled={!selected?.can_message}>Message agent</button><button className="activity-toggle" onClick={() => setShowActivity(true)}>Live signal</button><button className="icon-button" onClick={() => setSearchOpen(true)} title="Search">⌕</button><button className="icon-button" onClick={() => setSettingsOpen(true)} title="Change password">⚙</button></div></header>
      {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
      <div className="conversation" ref={listRef}><div className="conversation-inner">{jumpId != null && <div className="jump-banner">Showing search result <button onClick={() => setJumpId(null)}>Return to latest ↗</button></div>}<div ref={sentinelRef} className="older-marker">{older ? (loadingOlder ? 'Loading earlier messages…' : <button onClick={loadOlder}>Load earlier messages</button>) : 'Beginning of recorded history'}</div>
        {!items.length && <div className="empty-state"><div className="empty-icon">✦</div><h2>Direct line to {selected?.name}</h2><p>Messages are delivered to the current Herdr agent. Agent briefs posted through the local API appear here; the live pane is visible at right.</p></div>}
        <MessageList>{items.map(item => <MessageCard key={item.id} item={item} highlight={item.id === jumpId} onSendNow={setForceTarget} onInspect={() => setShowActivity(true)} />)}</MessageList>
      </div></div>
      <Composer channel={channel} onSend={send} pending={pending} setPending={setPending} disabled={!selected?.can_message} />
    </main>
    <aside className={`activity ${showActivity ? 'open' : ''}`}><div className="activity-head"><button className="close-activity" onClick={() => setShowActivity(false)} aria-label="Close live signal">×</button><div className="eyebrow">LIVE SIGNAL</div><h2>Agent activity</h2><p>Recent terminal output from the existing pane</p><div className="activity-live"><span className={`status-dot ${activityConnected ? 'working' : ''}`}/><strong>{activityConnected ? 'Connected' : 'Reconnecting'}</strong><span>· agent {activityStatus}</span><span>· {activityUpdated ? `refreshed ${activityUpdated.toLocaleTimeString()}` : 'waiting for first refresh'}</span></div></div><div className="activity-body" ref={activityRef}><pre>{activity || (activityConnected ? 'No recent output.' : 'Connecting to Herdr…')}</pre></div><div className="activity-foot">Recent terminal view · refreshes every 5 seconds. Agent presence is not project health; actual decisions are in posted briefs.</div></aside>
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
