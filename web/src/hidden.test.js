import assert from 'node:assert/strict';
import test from 'node:test';
import { BOARD_NOTE, hiddenNote, isHidden, visible } from './hidden.js';

test('crackdown rows are hidden by their labels, others stay', () => {
	assert.equal(isHidden('Crackdown'), true);
	assert.equal(isHidden('/home/hunter/workspace/crackdown-switch'), true);
	assert.equal(isHidden('poolrad-par-a', null, undefined), false);
	const { shown, hidden } = visible([{ id: 'poolrad' }, { id: 'crackdown' }], p => [p.id]);
	assert.deepEqual(shown, [{ id: 'poolrad' }]);
	assert.equal(hidden, 1);
	assert.equal(hiddenNote(0), '', 'nothing hidden says nothing');
	assert.match(hiddenNote(2), /^2 rows from a hidden project/);
	assert.match(BOARD_NOTE, /Crackdown/, 'the project is named once, at the top');
});
