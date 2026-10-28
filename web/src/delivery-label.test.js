import test from 'node:test';
import assert from 'node:assert/strict';
import { deliveryDuration, messageDeliveryLabel } from './delivery-label.js';

test('pickup timing supersedes the original stored outcome', () => {
  const item = { delivery: 'delivered', outcome: 'stored', delivered_at: 100, delivery_latency_s: 1.25 };
  assert.equal(messageDeliveryLabel(item), 'delivered in 1.3s');
  assert.equal(deliveryDuration({ ...item, delivery_latency_s: 0.03 }), '<0.1s');
});

test('missing, invalid, or merely stored receipts never manufacture elapsed delivery time', () => {
  const item = { delivery: 'stored', outcome: 'stored', delivered_at: 100, delivery_latency_s: 2 };
  assert.equal(messageDeliveryLabel(item), 'stored');
  assert.equal(deliveryDuration(item), null);
  for (const value of [undefined, null, '2', -1, NaN, Infinity]) {
    assert.equal(deliveryDuration({ ...item, delivery: 'delivered', delivery_latency_s: value }), null);
  }
  assert.equal(deliveryDuration({ ...item, delivery: 'delivered', delivered_at: null }), null);
});
