import assert from 'node:assert/strict';
import test from 'node:test';
import { age, num, stale, tokens, usd, wait, why } from './format.js';

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

test('tokens and dollars keep zero and cannot-compute apart', () => {
	assert.equal(tokens({ value: 2_154_599_040, as_of: 'x', reason: null }), '2.2B');
	assert.equal(tokens(12_400), '12.4k');
	assert.equal(tokens(0), '0');
	assert.equal(tokens({ value: null, as_of: null, reason: 'pi absent' }), '—');
	assert.equal(usd({ value: 10.736, as_of: 'x', reason: null }), '$10.74');
	assert.equal(usd({ value: 0, as_of: 'x', reason: null }), '$0.00', 'a recorded zero is a number');
	assert.equal(usd({ value: 0.0012, as_of: 'x', reason: null }), '$0.001');
	assert.equal(usd({ value: null, as_of: null, reason: 'tokens only' }), '—', 'never $0 for unknown');
});

test('a panel older than 15 minutes is stale, and so is one with no time', () => {
	const now = Date.parse('2026-10-23T12:00:00Z');
	assert.equal(stale('2026-10-23T11:50:00Z', now), false);
	assert.equal(stale('2026-10-23T11:44:59Z', now), true);
	assert.equal(stale(null, now), true, 'no as_of is never current');
	assert.equal(stale('not a date', now), true);
});

test('waits read in human units and unknown stays unknown', () => {
	assert.equal(wait(3.94), '3.9s');
	assert.equal(wait({ value: 54.2, as_of: 'x', reason: null }), '54s');
	assert.equal(wait(720), '12m');
	assert.equal(wait(14670.2), '4.1h');
	assert.equal(wait({ value: null, as_of: null, reason: 'no sends' }), '—');
});
