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
