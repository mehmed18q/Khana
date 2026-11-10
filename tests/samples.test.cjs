const { test } = require('node:test');
const assert = require('node:assert/strict');
const { sample, expand } = require('../reader/web/samples.js');

test('samples cover editable formats and include valid structured examples', () => {
  for (const format of ['Markdown', 'HTML', 'JSON', 'YAML', 'XML', 'CONF', 'LOG', 'Word'])
    assert.ok(sample(format)?.length > 20, format);
  assert.equal(JSON.parse(sample('JSON')).items[0].id, 1);
  assert.match(sample('HTML'), /^<!doctype html>[\s\S]*<meta charset="UTF-8">[\s\S]*<\/html>\n$/);
  assert.match(sample('XML'), /^<\?xml[\s\S]*<\/document>\n$/);
  assert.equal(sample('PDF'), null);
});

test('Tab expansion is scoped to a complete abbreviation at the caret', () => {
  assert.deepEqual(expand('doc', 3, 3, 'HTML'), { start: 0, end: 3 });
  assert.deepEqual(expand('before\n  sample', 15, 15, 'JSON'), { start: 9, end: 15 });
  for (const value of ['mydoc', 'text doc', 'documentation', 'sample ', 'doc\t'])
    assert.equal(expand(value, value.length, value.length, 'HTML'), null);
  assert.equal(expand('doc', 3, 3, 'Markdown'), null);
  assert.equal(expand('sample', 0, 6, 'HTML'), null);
});
