const { test } = require('node:test');
const assert = require('node:assert/strict');
const { index, get, position } = require('../reader/web/source-text.js');

test('source indexes preserve empty and trailing lines and Unicode columns', () => {
  const text = index('سلام 😀 world\n\nlast\n');
  assert.deepEqual(text.starts, [0, 14, 15, 20]);
  assert.equal(text.lines.length, 4);
  assert.equal(text.words, 3);
  assert.deepEqual(position(text, 7), { line: 0, column: 6 });
  assert.deepEqual(position(text, 20), { line: 3, column: 0 });
  assert.deepEqual(position(index(''), 0), { line: 0, column: 0 });
});

test('caret navigation reuses the index and source changes invalidate it', () => {
  const field = { value: 'one\ntwo' },
    first = get(field);
  assert.equal(get(field), first);
  field.value = 'one\nthree\nfour';
  assert.notEqual(get(field), first);
  assert.equal(get(field).words, 3);
  assert.deepEqual(position(get(field), 10), { line: 2, column: 0 });
});
