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
  for (const marker of ['Owner snapshot', 'Agents', 'Operations board', 'Original C bodies']) {
    assert.ok(bundle.includes(marker), `built bundle is missing ${JSON.stringify(marker)} - the nav may be in a component nothing renders`);
  }
});
