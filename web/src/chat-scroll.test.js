import test from 'node:test';
import assert from 'node:assert/strict';
import { isNearBottom, shouldFollow } from './chat-scroll.js';

const pane = (scrollTop, scrollHeight = 2000, clientHeight = 600) => ({ scrollTop, scrollHeight, clientHeight });

test('case 1: a scrolled-up reader is not pulled down by a new message', () => {
  const view = pane(200); // far from the bottom
  assert.equal(isNearBottom(view), false);
  assert.equal(shouldFollow({ atBottom: isNearBottom(view) }), false);
});

test('case 2: an at-bottom reader follows a new message', () => {
  const view = pane(1400); // 2000 - 1400 - 600 = 0
  assert.equal(isNearBottom(view), true);
  assert.equal(shouldFollow({ atBottom: isNearBottom(view) }), true);
});

test('the explicit affordance or own send always goes to the bottom', () => {
  const view = pane(200);
  assert.equal(shouldFollow({ atBottom: isNearBottom(view), ownSend: true }), true);
  assert.equal(shouldFollow({ atBottom: isNearBottom(view), jump: true }), true);
});
