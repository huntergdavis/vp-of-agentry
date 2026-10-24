import React from 'react';
import { num, why } from './format.js';
import { Absent } from './cost-panels.jsx';
import { Stamp } from './delivery-panels.jsx';

// Owner #1386: CREDITED, REPLACED and the per-day rate, from the snapshot
// (tools/credit_stats.py). Nothing here is hand-entered: every number comes
// from a committed file or its git history.

function signed(c) {
  const value = c != null && typeof c === 'object' ? c.value : c;
  if (value == null) return '—';
  return value > 0 ? `+${value}` : String(value);
}

export function CreditedPanel({ section }) {
  if (!section) return <Absent title="Credited" panel="credited" />;
  return <div className="snapshot-costs" data-panel="credited">
    <h3>Credited</h3>
    <Stamp section={section} />
    {section.status !== 'ok' && <div className="snapshot-missing">{section.reason}</div>}
    {section.status === 'ok' && <>
      <div className="credit-big"><b>{num(section.value)}</b> <span>strict C bodies</span>
        <small>{signed(section.delta_24h)} in 24 h · {signed(section.delta_7d)} in 7 days · last changed {section.committed_at ? new Date(section.committed_at).toLocaleString() : '—'}</small></div>
      {why(section.delta_24h) && <small className="cost-reason">24 h: {why(section.delta_24h)}</small>}
      <div className="snapshot-backlog-counts">{(section.by_kind || []).map(k => <span key={k.kind}><b>{num(k.count)}</b> {k.kind}</span>)}</div>
      {section.kind_mismatch && <div className="snapshot-missing">{section.kind_mismatch}</div>}
    </>}
    {section.truth && <div className="snapshot-truth">{section.truth}</div>}
  </div>;
}

export function ReplacedPanel({ section }) {
  if (!section) return <Absent title="Replaced" panel="replaced" />;
  return <div className="snapshot-costs" data-panel="replaced">
    <h3>Replaced</h3>
    <Stamp section={section} />
    {section.status === 'ok'
      ? <div className="credit-big"><b>{num(section.value)}</b> <span>bodies the game runs as our C, proven by an identical run</span>
          {section.not_counted?.value ? <small>{num(section.not_counted)} listed but not counted (no zero-difference proof)</small> : null}</div>
      : <div className="credit-big"><b>—</b> <span className="snapshot-missing">{section.reason}</span></div>}
    {section.contract && <small className="cost-reason">A lane reports it by writing <code>{section.contract.path}</code> in poolrad-decomp: one record per body with <code>proven_at</code> and <code>evidence.differing = 0</code>.</small>}
    {section.truth && <div className="snapshot-truth">{section.truth}</div>}
  </div>;
}

/** Net change per day as bars; a day with no known value is a gap, never a zero bar. */
function DayBars({ days, label }) {
  if (!days) return null;
  const values = days.map(d => d.net).filter(v => v != null);
  const top = Math.max(1, ...values.map(Math.abs));
  const w = 14, gap = 4, h = 48;
  return <figure className="credit-bars">
    <svg viewBox={`0 0 ${days.length * (w + gap)} ${h + 14}`} role="img" aria-label={`${label}: net per day over ${days.length} days`}>
      {days.map((d, i) => d.net == null
        ? <text key={d.day} x={i * (w + gap) + w / 2} y={h} textAnchor="middle" className="credit-gap">·</text>
        : <rect key={d.day} x={i * (w + gap)} y={h - Math.max(1, (Math.abs(d.net) / top) * h)} width={w}
            height={Math.max(1, (Math.abs(d.net) / top) * h)} className={d.net < 0 ? 'neg' : ''}><title>{d.day}: {signed(d.net)} ({d.events} events)</title></rect>)}
      <text x="0" y={h + 12} className="credit-axis">{days[0].day.slice(5)}</text>
      <text x={days.length * (w + gap) - gap} y={h + 12} textAnchor="end" className="credit-axis">{days.at(-1).day.slice(5)}</text>
    </svg>
    <figcaption>{label}</figcaption>
  </figure>;
}

export function RatePanel({ section }) {
  if (!section) return <Absent title="Rate per day" panel="credit-rate" />;
  return <div className="snapshot-costs" data-panel="credit-rate">
    <h3>Rate per day · last {section.days} days</h3>
    <Stamp section={section} />
    <div className="snapshot-backlog-counts">
      <span>credited <b>{num(section.credited_per_day_7d)}</b>/day (7-day mean)</span>
      <span>replaced <b>{num(section.replaced_per_day_7d)}</b>/day</span>
    </div>
    <div className="credit-rate-row">
      {section.credited ? <DayBars days={section.credited} label="credited, net per day" /> : <div className="snapshot-missing">credited: {section.credited_reason}</div>}
      {section.replaced ? <DayBars days={section.replaced} label="replaced, net per day" /> : <div className="snapshot-missing">replaced: {section.replaced_reason}</div>}
    </div>
    {(section.largest_steps || []).length > 0 && <small className="cost-reason">Largest single commits: {section.largest_steps.map(s => `${s.change > 0 ? '+' : ''}${s.change} on ${new Date(s.at).toLocaleDateString()} (${s.subject})`).join(' · ')}. A batch publication is one commit, not a day of work.</small>}
    <div className="snapshot-truth">{section.method} A dot is a day before the checkpoint existed, not a zero.</div>
  </div>;
}
