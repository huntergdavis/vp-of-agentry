import test from 'node:test';
import assert from 'node:assert';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// The check that catches dead-code UI: assert the BUILT bundle contains the
// strings the live feature renders. A "dist newer than src" check would not
// catch a component that nothing renders (Rollup tree-shakes it away).
const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, '..', 'dist', 'assets');

test('the built bundle contains the live dashboard nav', () => {
  const bundle = readdirSync(assets)
    .filter(name => name.endsWith('.js'))
    .map(name => readFileSync(join(assets, name), 'utf8'))
    .join('\n');
  for (const marker of ['Operations', 'Play Pool of Radiance', 'VP of Agentry', 'Agents']) {
    assert.ok(bundle.includes(marker), `built bundle is missing ${JSON.stringify(marker)} - the nav may be in a component nothing renders`);
  }
});

test('no page renders its own row of dashboard links (the left bar is the only nav)', () => {
  const source = readFileSync(join(here, 'main.jsx'), 'utf8');
  assert.ok(!source.includes('href={`/dash/${key}`}'), 'must not link /dash/<key> (server 302s without a session)');
  assert.ok(!source.includes('DashNav') && !source.includes('DashHeader'), 'header link layers must stay deleted');
  assert.ok(!source.includes('dash-nav-links'), 'no link row above or inside page content');
});


test('the composer stores what was typed: turndown escaping stays off', () => {
  const source = readFileSync(join(here, 'main.jsx'), 'utf8');
  assert.ok(source.includes('td.escape = text => text'), 'turndown would turn [x] into \\[x\\] and eat markdown characters');
});
