import test from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// The guard that would have caught Desk, the missing nav, and the dead
// OpsBoard/PoolradProgress: a component defined in main.jsx but never rendered
// is tree-shaken away, so a developer edits source and the page ignores it.
const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, 'main.jsx'), 'utf8');

const components = [...source.matchAll(/^function ([A-Z][A-Za-z0-9_]*)\s*\(/gm)].map(m => m[1]);

function bodyOf(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) return '';
  const next = source.indexOf('\nfunction ', start + 1);
  return next < 0 ? source.slice(start) : source.slice(start, next);
}

test('every top-level component defined in main.jsx is reachable from App', () => {
  const reachable = new Set(['App']);
  const queue = ['App'];
  while (queue.length) {
    const current = queue.pop();
    for (const match of bodyOf(current).matchAll(/<([A-Z][A-Za-z0-9_]*)/g)) {
      if (!reachable.has(match[1])) {
        reachable.add(match[1]);
        queue.push(match[1]);
      }
    }
  }
  const dead = components.filter(name => name !== 'App' && !reachable.has(name));
  assert.deepEqual(dead, [], `components defined but never rendered from App: ${dead.join(', ')}`);
});

test('the nav lists exactly the five live routes', () => {
  const routes = [...source.matchAll(/^  ([a-z]+): \{ eyebrow:/gm)].map(m => m[1]).sort();
  assert.deepEqual(routes, ['agents', 'cos', 'operations', 'play', 'vp']);
});
