import React, { useState } from 'react';
import { age, num, tokens, usd, why } from './format.js';

// Three owner panels rendered from the snapshot (tools/agent_costs.py). No
// live reads: every number is a {value, as_of, reason} cell, and a null cell
// shows its reason on the page, not only in a tooltip.

function Missing({ cell }) {
  const reason = why(cell);
  return reason ? <small className="cost-reason">{reason}</small> : null;
}

function Truth({ text }) {
  return text ? <div className="snapshot-truth">{text}</div> : null;
}

export function CostPerAgent({ section }) {
  const [all, setAll] = useState(false);
  if (!section) return null;
  const rows = section.rows || [];
  const shown = all ? rows : rows.slice(0, 12);
  const reasons = [...new Set(rows.map(r => why(r.usd_month)).filter(Boolean))];
  return <div className="snapshot-costs" data-panel="cost-per-agent">
    <h3>Cost per agent</h3>
    <small>{section.windows?.month} · and the last 24 hours · scanned {section.as_of ? `${age(section.as_of)} ago` : '—'}</small>
    {section.status !== 'ok' && <div className="snapshot-missing">{section.reason || Object.entries(section.failed_sources || {}).map(([h, r]) => `${h}: ${r}`).join('; ')}</div>}
    <div className="snapshot-table"><table>
      <thead><tr><th>Agent (harness · checkout)</th><th>Dollars this month</th><th>Dollars 24h</th><th>Tokens this month</th><th>Fresh this month</th><th>Tokens 24h</th><th>Sessions</th><th>Panes there now</th></tr></thead>
      <tbody>{shown.map(r => <tr key={`${r.harness}:${r.checkout}`}>
        <td title={r.checkout}>{r.label}</td>
        <td>{r.usd_month?.value != null ? usd(r.usd_month) : <span title={why(r.usd_month)}>tokens only</span>}</td>
        <td>{r.usd_24h?.value != null ? usd(r.usd_24h) : <span title={why(r.usd_24h)}>tokens only</span>}</td>
        <td>{tokens(r.tokens_month)}</td><td title="input + cache writes + output; excludes cache reads">{tokens(r.fresh_tokens_month)}</td><td>{tokens(r.tokens_24h)}</td>
        <td>{num(r.sessions_month)}</td>
        <td>{r.panes == null ? <span title={section.panes_reason}>unknown</span> : r.panes.length ? r.panes.join(', ') : 'none'}</td>
      </tr>)}{!rows.length && <tr><td colSpan="8">No harness sessions this month.</td></tr>}</tbody>
    </table></div>
    {rows.length > 12 && <button className="cost-more" onClick={() => setAll(!all)}>{all ? 'Show the top 12' : `Show all ${rows.length} (sorted by tokens this month)`}</button>}
    {reasons.map(r => <small className="cost-reason" key={r}>"tokens only": {r}.</small>)}
    <Truth text={section.truth} />
  </div>;
}

export function FreeModelVolume({ section }) {
  if (!section) return null;
  if (section.status !== 'ok') return <div className="snapshot-costs" data-panel="free-model-volume"><h3>Free-model work volume</h3><div className="snapshot-missing">{section.reason}</div></div>;
  const models = section.models || [];
  return <div className="snapshot-costs" data-panel="free-model-volume">
    <h3>Free-model work volume</h3>
    <div className="snapshot-backlog-counts">
      <span><b>{num(section.runs_month)}</b> runs this month</span>
      <span><b>{num(section.runs_24h)}</b> in 24h</span>
      <span><b>{num(section.outcomes_recorded)}</b> reviewed outcomes recorded</span>
    </div>
    <Missing cell={section.outcomes_recorded} />
    <div className="snapshot-table"><table>
      <thead><tr><th>Free model</th><th>Runs this month</th><th>Runs 24h</th><th>No output</th><th>Output tokens</th><th>Via</th></tr></thead>
      <tbody>{models.map(m => <tr key={m.model}><td>{m.model}</td><td>{num(m.runs_month)}</td><td>{num(m.runs_24h)}</td><td title="sessions this month that got no output back - usually an endpoint failure">{num(m.runs_no_output_month)}</td><td>{tokens(m.output_tokens_month)}</td><td>{(m.harnesses || []).join(', ')}</td></tr>)}
        {!models.length && <tr><td colSpan="6">No free-model runs this month.</td></tr>}</tbody>
    </table></div>
    {section.outcomes && <div className="snapshot-table"><table>
      <thead><tr><th>Reviewed outcomes (ledger)</th><th>Accepted</th><th>After rework</th><th>Rejected</th><th>Failed</th></tr></thead>
      <tbody>{section.outcomes.map(o => <tr key={o.model}><td>{o.model}</td><td>{num(o.accepted)}</td><td>{num(o.accepted_after_rework)}</td><td>{num(o.rejected)}</td><td>{num(o.failed)}</td></tr>)}</tbody>
    </table></div>}
    <small>{section.method}. Outcomes from {section.outcomes_source}.</small>
    <Truth text={section.truth} />
  </div>;
}

function percent(c) {
  return c?.value != null ? `${Math.round(c.value)}% used` : '—';
}

function resets(at) {
  if (at == null) return '';
  const when = typeof at === 'number' ? new Date(at * 1000) : new Date(at);
  return Number.isNaN(when.getTime()) ? '' : ` · resets ${when.toLocaleString()}`;
}

export function UsagePanel({ section }) {
  if (!section) return null;
  const providers = section.providers || [];
  const subs = section.subscriptions || [];
  return <div className="snapshot-costs" data-panel="usage">
    <h3>Overall usage</h3>
    {section.status !== 'ok' && <div className="snapshot-missing">{section.reason || section.status}</div>}
    <div className="cost-usage-grid">
      {providers.map(p => <div className="cost-usage-card" key={p.provider}>
        <b>{(p.provider || 'unknown').toUpperCase()}</b>
        <small>{p.meaning === 'percent_used' ? 'provider window' : p.meaning === 'local_session_estimate' ? 'local estimate' : p.meaning || ''} · read {p.as_of ? `${age(p.as_of)} ago` : '—'}</small>
        {p.reason && <div className="snapshot-missing">{p.reason}</div>}
        {(p.windows || []).map(w => <div key={w.name} className="cost-window"><span>{w.name}</span><strong>{percent(w.percent_used)}</strong><small>{resets(w.resets_at)}</small><Missing cell={w.percent_used} /></div>)}
        {p.extra_usage && <div className="cost-window extra"><span>extra usage billed</span><strong>{usd(p.extra_usage.used)} of {usd(p.extra_usage.limit)}</strong><small>{p.extra_usage.currency} · {p.extra_usage.truth}</small></div>}
        {p.truth && <Truth text={p.truth} />}
      </div>)}
      {!providers.length && <div className="muted">No provider reading stored.</div>}
    </div>
    <div className="cost-subs"><h4>Fixed subscriptions (owner-reported, monthly)</h4>
      {subs.length ? <ul>{subs.map(s => <li key={s.provider}><b>{s.provider}</b> {usd(s.monthly_usd)}/month</li>)}</ul> : <div className="snapshot-missing">no subscription recorded</div>}
    </div>
    <Truth text={section.truth} />
  </div>;
}
