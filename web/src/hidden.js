/**
 * Projects hidden from the operations board (owner #1381, 2026-10-23).
 *
 * Crackdown panels hidden 2026-10-23 at owner request; data retained; reason:
 * port shelved. The collector still writes every Crackdown field to the
 * snapshot and the history stays in the database: this hides the rendering
 * only. Remove the entry to bring it back.
 */
export const HIDDEN_PROJECTS = ['crackdown'];

/** True when any of the given labels names a hidden project. */
export function isHidden(...labels) {
	return labels.some(label => typeof label === 'string'
		&& HIDDEN_PROJECTS.some(word => label.toLowerCase().includes(word)));
}

/** Split rows into those shown and a count of those hidden, so a table can say what it left out. */
export function visible(rows, labels) {
	const shown = [];
	let hidden = 0;
	for (const row of rows || []) {
		if (isHidden(...labels(row))) hidden += 1; else shown.push(row);
	}
	return { shown, hidden };
}

/** Per-table count; the project is named once, at the top of the board (BOARD_NOTE). */
export function hiddenNote(count) {
	return count ? `${count} row${count === 1 ? '' : 's'} from a hidden project not shown` : '';
}

export const BOARD_NOTE = 'Crackdown is hidden from this board (owner #1381, 2026-10-23: port shelved). Its data is still collected and kept.';
