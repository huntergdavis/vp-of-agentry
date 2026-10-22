import assert from 'node:assert/strict';
import test from 'node:test';
import { age, num, why } from './format.js';

test('a plain number renders as itself, not as cannot-compute', () => {
	// The regression: backlog counts are plain ints, the helper expected cells,
	// so the owner saw "— open — in progress — blocked" over correct data.
	assert.equal(num(6), 6);
	assert.equal(num(0), 0, 'zero is a number the owner will believe');
	assert.equal(num({ value: 6, as_of: '2026-10-22T00:00:00Z', reason: null }), 6);
});

test('a null cell renders as cannot-compute and keeps its reason', () => {
	assert.equal(num({ value: null, as_of: null, reason: 'store absent' }), '—');
	assert.equal(num(null), '—');
	assert.equal(num(undefined), '—');
	assert.equal(why({ value: null, as_of: null, reason: 'store absent' }), 'store absent');
	assert.equal(why(6), '');
});

test('age is in the units a person reads', () => {
	const now = Date.parse('2026-10-22T12:00:00Z');
	assert.equal(age('2026-10-22T11:59:30Z', now), '30s');
	assert.equal(age('2026-10-22T11:50:00Z', now), '10m');
	assert.equal(age('2026-10-22T02:00:00Z', now), '10h');
	assert.equal(age('2026-10-20T12:00:00Z', now), '2d');
});
