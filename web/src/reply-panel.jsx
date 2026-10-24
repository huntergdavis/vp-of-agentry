import React from 'react';
import { num, wait } from './format.js';
import { Absent } from './cost-panels.jsx';
import { Stamp } from './delivery-panels.jsx';
import { hiddenNote, visible } from './hidden.js';

// Reply-latency leaderboard for every agent with a mailbox
// (tools/reply_latency.py). Sits beside the cost board: speed and cost for
// the same agents in one glance.

export function ReplyLeaderboard({ section }) {
  if (!section) return <Absent title="Reply speed" panel="reply-leaderboard" />;
  const kept = visible(section.rows, r => [r.label, r.mailbox]);
  const rows = kept.shown;
  let rank = 0;
  return <div className="snapshot-costs" data-panel="reply-leaderboard">
    <h3>Reply speed · every agent with a mailbox</h3>
    <Stamp section={section} />
    <div className="reply-deterministic">{section.deterministic} Window: {section.window}.</div>
    {section.status !== 'ok' && <div className="snapshot-missing">{section.reason}</div>}
    {section.panes_reason && <div className="snapshot-missing">{section.panes_reason}</div>}
    <div className="snapshot-table"><table>
      <thead><tr><th>#</th><th>Agent</th><th>p50</th><th>p90</th><th>Max</th><th>Handled 24h</th><th>Unhandled 24h</th><th>Silent</th><th>Oldest silent</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.mailbox} className={r.silent?.value ? 'delivery-late' : ''}>
        <td>{r.ranked ? ++rank : ''}</td>
        <td>{r.label}{r.pane_open === false ? <small> · pane closed</small> : null}</td>
        <td>{r.p50_s?.value != null ? <b>{wait(r.p50_s)}</b> : <span className="leader-null">{r.p50_s?.reason}</span>}</td>
        <td>{wait(r.p90_s)}</td><td>{wait(r.max_s)}</td>
        <td>{num(r.handled)}</td><td>{num(r.unhandled_24h)}</td>
        <td title={r.silent_rule}><b>{num(r.silent)}</b></td>
        <td>{r.oldest_silent ? `${r.oldest_silent.id} · ${wait(r.oldest_silent.age_s)}` : '—'}</td>
      </tr>)}{!rows.length && <tr><td colSpan="9">No mailbox traffic.</td></tr>}</tbody>
    </table></div>
    {hiddenNote(kept.hidden) && <small className="cost-reason">{hiddenNote(kept.hidden)}.</small>}
    <small className="cost-reason">{section.method} Silent: open longer than 3x the agent's own p50; with no handled message, every open message counts.</small>
    {section.truth && <div className="snapshot-truth">{section.truth}</div>}
  </div>;
}
