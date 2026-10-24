import React from 'react';
import { age, num, why } from './format.js';
import { Absent } from './cost-panels.jsx';
import { Stamp } from './delivery-panels.jsx';

// Owner #1426: free-model leaderboard, ranked by verified output rather than
// runs (tools/free_leaderboard.py). Accepted and assisted lines stay null with
// their reason until a file attributes lines to a model.

function NullCell({ cell }) {
  return cell?.value != null ? num(cell) : <span className="leader-null" title={why(cell)}>no data</span>;
}

export function FreeLeaderboard({ section }) {
  if (!section) return <Absent title="Free-model leaderboard" panel="free-leaderboard" />;
  const rows = section.rows || [];
  const lineReason = rows.length ? why(rows[0].accepted_lines) : '';
  return <div className="snapshot-costs" data-panel="free-leaderboard">
    <h3>Free-model leaderboard</h3>
    <Stamp section={section} />
    {section.status === 'nulled' && <div className="snapshot-missing">{section.reason}</div>}
    {section.status === 'ok' || section.status === 'partial' ? <>
      <div className="snapshot-backlog-counts">
        <span><b>{num(section.verified_decodes)}</b> verified decodes</span>
        <span>from <b>{num(section.attempts)}</b> attempts</span>
      </div>
      <div className="snapshot-table"><table>
        <thead><tr><th>#</th><th>Model</th><th>Tier</th><th>Verified bytes</th><th>Verified decodes</th><th>Accepted lines</th><th>Assisted lines</th><th>Runs</th><th>Empty</th><th>No dump</th><th>Wrong bytes</th><th>Unchecked</th><th>Last seen</th></tr></thead>
        <tbody>{rows.map((r, i) => <tr key={r.model}>
          <td>{i + 1}</td><td>{r.model}</td><td className={`leader-tier ${r.tier}`}>{r.tier}</td>
          <td><b>{num(r.verified_bytes)}</b></td>
          <td>{num(r.verified_decodes)} <small>of {num(r.runs)}</small></td>
          <td><NullCell cell={r.accepted_lines} /></td><td><NullCell cell={r.assisted_lines} /></td>
          <td>{num(r.runs)}</td><td>{num(r.empty)}</td><td>{num(r.no_dump)}</td><td>{num(r.wrong_bytes)}</td><td>{num(r.unchecked)}</td>
          <td>{r.last_seen ? `${age(r.last_seen)} ago` : '—'}</td>
        </tr>)}</tbody>
      </table></div>
      {lineReason && <small className="cost-reason">Accepted and assisted lines: {lineReason}.</small>}
      {(section.problems || []).length > 0 && <small className="cost-reason">Unread attempts: {section.problems.join('; ')}</small>}
      <small className="cost-reason">{section.method} Tier: free = catalog id ends in :free or -free; subscription = the fixed OpenCode Go plan; metered = billed per token.</small>
    </> : null}
    <div className="leader-truth">{section.truth}</div>
  </div>;
}
