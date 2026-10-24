import React from 'react';
import { age, num, stale, wait, why } from './format.js';
import { Absent } from './cost-panels.jsx';
import { hiddenNote, visible } from './hidden.js';

// Owner #1358: current dunks, inbox metrics, delivery latency and health,
// rendered from the snapshot (tools/delivery_stats.py). Every panel names its
// source and as_of, and says STALE when the reading is over 15 minutes old.

export function Stamp({ section }) {
  if (!section) return null;
  const old = stale(section.as_of);
  return <div className={`delivery-stamp${old ? ' stale' : ''}`}>
    {old && <b>STALE · </b>}
    {section.as_of ? `as of ${new Date(section.as_of).toLocaleString()} (${age(section.as_of)} ago)` : 'no reading time'}
    {section.source && <> · source <code>{section.source}</code></>}
  </div>;
}

function Unavailable({ section }) {
  return section && section.status === 'nulled'
    ? <div className="snapshot-missing">{section.reason || 'source unavailable'}</div> : null;
}

function when(stamp) {
  return stamp ? new Date(stamp).toLocaleString() : '—';
}

export function DunksPanel({ section }) {
  if (!section) return <Absent title="Current dunks" panel="dunks" />;
  const kept = visible(section.rows, d => [d.name, d.target?.workspace, d.target?.label]);
  const rows = kept.shown;
  return <div className="snapshot-costs" data-panel="dunks">
    <h3>Current dunks · {rows.length}</h3>
    <Stamp section={section} /><Unavailable section={section} />
    <div className="snapshot-table"><table>
      <thead><tr><th>ID</th><th>Target</th><th>Every</th><th>State</th><th>Gates</th><th>Last fired</th><th>Next</th><th>Sent / skipped / held</th><th>Text</th></tr></thead>
      <tbody>{rows.map(d => <tr key={d.id} className={d.overdue_min ? 'delivery-late' : ''}>
        <td><b>{d.id}</b>{d.name ? <small> {d.name}</small> : null}</td>
        <td>{d.target?.label || '—'} <small>{d.target?.pane} · {d.target?.agent}</small></td>
        <td>{d.every_min != null ? `${d.every_min}m` : '—'}</td>
        <td>{d.state}{d.overdue_min ? <small> · {d.overdue_min} min overdue</small> : null}{d.last_error ? <small className="cost-reason">{d.last_error}</small> : null}</td>
        <td>{(d.gate || []).join(', ') || 'none'}</td>
        <td>{when(d.last_sent_at)}</td>
        <td>{d.running ? when(d.next_send_at) : 'not running'}</td>
        <td>{d.sent ?? '—'} / {d.skips ?? '—'} / {d.holds ?? '—'}</td>
        <td className="delivery-text" title={d.text}>{d.text}</td>
      </tr>)}{!rows.length && <tr><td colSpan="9">{section.status === 'ok' ? 'No dunks are defined.' : 'Dunk list unreadable.'}</td></tr>}</tbody>
    </table></div>
    {hiddenNote(kept.hidden) && <small className="cost-reason">{hiddenNote(kept.hidden)}.</small>}
    {section.truth && <div className="snapshot-truth">{section.truth}</div>}
  </div>;
}

export function InboxPanel({ section }) {
  if (!section) return <Absent title="Inbox" panel="inbox" />;
  const keptBoxes = visible(section.mailboxes, b => [b.mailbox]);
  const boxes = keptBoxes.shown;
  const total = section.total || {};
  const notice = total.notice || {};
  return <div className="snapshot-costs" data-panel="inbox">
    <h3>Inbox</h3>
    <Stamp section={section} /><Unavailable section={section} />
    {section.status === 'ok' && <div className="snapshot-backlog-counts">
      <span><b>{num(total.unread)}</b> unread</span>
      <span>oldest <b>{total.oldest_unread_h?.value != null ? `${total.oldest_unread_h.value} h` : '—'}</b></span>
      <span><b>{num(total.arrived_24h)}</b> arrived in 24 h</span>
      <span>nudges: <b>{notice.sent ?? 0}</b> delivered · <b>{notice.queued ?? 0}</b> queued · <b>{notice.failed ?? 0}</b> failed · <b>{notice.none ?? 0}</b> none</span>
    </div>}
    <div className="snapshot-table"><table>
      <thead><tr><th>Mailbox</th><th>Unread</th><th>Oldest unread</th><th>Arrived 24h</th><th>Nudge delivered</th><th>Queued</th><th>Failed</th></tr></thead>
      <tbody>{boxes.map(b => <tr key={b.mailbox}>
        <td>{b.mailbox}</td><td>{num(b.unread)}</td>
        <td>{b.oldest_unread_h?.value != null ? `${b.oldest_unread_h.value} h` : '—'}</td>
        <td>{num(b.arrived_24h)}</td><td>{b.notice?.sent ?? 0}</td><td>{b.notice?.queued ?? 0}</td><td>{b.notice?.failed ?? 0}</td>
      </tr>)}{!boxes.length && <tr><td colSpan="7">No mailboxes.</td></tr>}</tbody>
    </table></div>
    {hiddenNote(keptBoxes.hidden) && <small className="cost-reason">{hiddenNote(keptBoxes.hidden)}; the totals above still include them.</small>}
    {section.truth && <div className="snapshot-truth">{section.truth}</div>}
  </div>;
}

export function DeliveryPanel({ latency, health }) {
  if (!latency && !health) return <Absent title="Delivery · arrival to delivery" panel="delivery" />;
  const all = latency?.all || {};
  const waiting = latency?.still_waiting || {};
  const keptHeld = visible(health?.held, h => [h.target]);
  const held = keptHeld.shown;
  const keptBoxes = visible(latency?.per_mailbox, m => [m.mailbox]);
  return <div className="snapshot-costs" data-panel="delivery">
    <h3>Delivery · arrival to delivery, last 24 h</h3>
    <Stamp section={latency} /><Unavailable section={latency} />
    {latency?.status === 'ok' && <div className="delivery-headline">
      <span>p50 <b>{wait(all.p50_s)}</b></span>
      <span>p90 <b>{wait(all.p90_s)}</b></span>
      <span>max <b>{wait(all.max_s)}</b></span>
      <span>n <b>{num(all.n)}</b></span>
      <span className={waiting.n?.value ? 'warn' : ''}>still waiting <b>{num(waiting.n)}</b>{waiting.oldest_s?.value != null ? <> · oldest <b>{wait(waiting.oldest_s)}</b></> : null}</span>
      <span>failed <b>{num(latency.failed_24h)}</b></span>
    </div>}
    {why(all.p50_s) && <small className="cost-reason">{why(all.p50_s)}</small>}
    {keptBoxes.shown.length > 0 && <div className="snapshot-table"><table>
      <thead><tr><th>Mailbox</th><th>Sends</th><th>p50</th><th>p90</th><th>Max</th></tr></thead>
      <tbody>{keptBoxes.shown.map(m => <tr key={m.mailbox}><td>{m.mailbox}</td><td>{num(m.n)}</td><td>{wait(m.p50_s)}</td><td>{wait(m.p90_s)}</td><td>{wait(m.max_s)}</td></tr>)}</tbody>
    </table></div>}
    {hiddenNote(keptBoxes.hidden + keptHeld.hidden) && <small className="cost-reason">{hiddenNote(keptBoxes.hidden + keptHeld.hidden)}; p50/p90/max above still include them.</small>}
    {(latency?.holds_24h || []).length > 0 && <small className="cost-reason">holds in 24 h: {latency.holds_24h.map(h => `${h.reason} ${num(h.count)} (${h.kind === 'dunk.held' ? 'dunk' : 'message'})`).join(' · ')}</small>}
    {latency?.truth && <div className="snapshot-truth">{latency.truth}</div>}
    <h4 className="delivery-sub">Held now · not yet delivered</h4>
    <Stamp section={health} /><Unavailable section={health} />
    {health?.panes_reason && <div className="snapshot-missing">Pane list unreadable ({health.panes_reason}): a message to a dead pane cannot be told apart from a held one.</div>}
    <div className="snapshot-table"><table>
      <thead><tr><th>Target</th><th>Reason</th><th>Waiting</th><th>Holds</th><th>Detail</th></tr></thead>
      <tbody>{held.map(h => <tr key={h.message_id || `${h.pane}-${h.waiting_s}`} className={(h.waiting_s || 0) > 3600 ? 'delivery-late' : ''}>
        <td>{h.target} <small>{h.pane}</small></td><td><b>{h.reason}</b></td><td>{wait(h.waiting_s)}</td><td>{h.holds ?? '—'}</td>
        <td className="delivery-text" title={h.text}>{h.detail || h.text}</td>
      </tr>)}{!held.length && <tr><td colSpan="5">{health?.status === 'nulled' ? 'Queue unreadable.' : 'Nothing is held.'}</td></tr>}</tbody>
    </table></div>
    {health?.truth && <div className="snapshot-truth">{health.truth}</div>}
  </div>;
}
