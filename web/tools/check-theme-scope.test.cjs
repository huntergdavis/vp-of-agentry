const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {checkThemeScope, checkDirectory} = require('./check-theme-scope.cjs');

test('repository variants remain constrained to their own theme', () => {
  assert.deepEqual(checkDirectory(path.join(__dirname, '../src/themes')), []);
});

test('default base is exempt; numeric IDs and scoped selector lists work', () => {
  assert.deepEqual(checkThemeScope(':root { --ink: black } body { color: black }', 'default'), []);
  assert.deepEqual(checkThemeScope(`
    :root[data-theme="2001"] { --ink: black }
    @media print {
      :root[data-theme='2001'] body::after,
      :root[data-theme=2001] :is(h1, h2, .brand) { display: none }
    }
  `, '2001'), []);
});

test('unscoped selector branch fails even beside a scoped branch', () => {
  const errors = checkThemeScope(':root[data-theme="nostromo"] h1, body { color: red }', 'nostromo');
  assert.equal(errors.length, 1);
  assert.match(errors[0], /unscoped selector: body$/);
});

test('nested conditional leaks and another theme root fail', () => {
  const errors = checkThemeScope(`
    @media print { @supports (display: grid) { body { color: red } } }
    :root[data-theme="crt"] { --ink: red }
    :root { --surface: red }
  `, 'nostromo');
  assert.equal(errors.length, 3);
});

test('a textual prefix inside a different theme ID does not grant scope', () => {
  assert.equal(checkThemeScope(':root[data-theme="crt-extra"] { color: red }', 'crt').length, 1);
});

test('variant imports cannot introduce unchecked global selectors', () => {
  assert.match(checkThemeScope('@import "global.css";', 'crt')[0], /bypasses scope checks/);
});
