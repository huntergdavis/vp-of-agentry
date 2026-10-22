/**
 * Number formatting for the owner page.
 *
 * Every number in the snapshot is a cell {value, as_of, reason}, but a few
 * counters are plain numbers. A helper that only understood cells turned every
 * backlog count into an em-dash: the page looked empty while the data was right.
 * "Cannot compute" and "six" must never render the same.
 */
export function num(c) {
	if (c != null && typeof c === 'object') return c.value != null ? c.value : '—';
	return c != null ? c : '—';
}

/** A cell's reason, or empty when the cell is a healthy number. */
export function why(c) {
	return c != null && typeof c === 'object' && c.value == null ? (c.reason || 'no value') : '';
}

export function age(stamp, now = Date.now()) {
	const seconds = Math.max(0, (now - new Date(stamp).getTime()) / 1000);
	if (seconds < 90) return `${Math.round(seconds)}s`;
	if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
	if (seconds < 172800) return `${Math.round(seconds / 3600)}h`;
	return `${Math.round(seconds / 86400)}d`;
}

/** Token counts in the units a person reads: 950, 12.4k, 3.1M, 2.2B. A null cell stays an em-dash. */
export function tokens(c) {
	const value = c != null && typeof c === 'object' ? c.value : c;
	if (value == null) return '—';
	const units = [[1e9, 'B'], [1e6, 'M'], [1e3, 'k']];
	for (const [size, unit] of units) if (Math.abs(value) >= size) return `${(value / size).toFixed(1)}${unit}`;
	return String(value);
}

/** Dollars from a cell. $0.00 is a recorded zero; a null cell is an em-dash, never $0. */
export function usd(c) {
	const value = c != null && typeof c === 'object' ? c.value : c;
	if (value == null) return '—';
	return `$${value.toFixed(value !== 0 && Math.abs(value) < 1 ? 3 : 2)}`;
}
