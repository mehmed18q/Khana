const { test } = require('node:test');
const assert = require('node:assert/strict');
const { matches, replacement } = require('../reader/web/search.js');
const slices = (text, query, options) =>
  matches(text, query, options).map(({ start, end }) => text.slice(start, end));
const apply = (text, operation) =>
  text.slice(0, operation.start) + operation.text + text.slice(operation.end);

test('literal search preserves spaces, punctuation and regexp metacharacters', () => {
  for (const query of ['a.b', '[a]', '(a)', '$&', '\\', 'x+y?', '^a$', '{a}', 'a|b'])
    assert.deepEqual(slices(`prefix ${query} suffix`, query), [query]);
  assert.deepEqual(slices('prefix   suffix', ' '), [' ', ' ', ' ']);
  assert.deepEqual(matches('text', ''), []);
  assert.deepEqual(matches('text', 'missing'), []);
});
test('case insensitive search keeps exact UTF-16 offsets after length-changing letters', () => {
  const text = 'İ 😀 Cat cat CAT K k Σ σ ς';
  assert.deepEqual(slices(text, 'cat'), ['Cat', 'cat', 'CAT']);
  assert.deepEqual(matches(text, 'cat')[0], { start: 5, end: 8 });
  assert.deepEqual(slices(text, 'cat', { matchCase: true }), ['cat']);
  assert.deepEqual(slices(text, 'k'), ['K', 'k']);
  assert.deepEqual(slices(text, 'σ'), ['Σ', 'σ', 'ς']);
});
test('whole word recognizes Persian, marks, digits, underscores and joiners', () => {
  assert.deepEqual(
    slices('سلام سلامتی (سلام) سلام\u200cها اسلام سلام_دوست سلام۱', 'سلام', { wholeWord: true }),
    ['سلام', 'سلام']
  );
  assert.deepEqual(
    slices('cat cats _cat cat_ cat2 2cat (cat) cat\u0301 𐐀cat cat𐐀', 'cat', { wholeWord: true }),
    ['cat', 'cat']
  );
  assert.deepEqual(slices('a سلام\u200cها b', 'سلام\u200cها', { wholeWord: true }), [
    'سلام\u200cها',
  ]);
});
test('search returns non-overlapping matches without a 2000-result limit', () => {
  assert.deepEqual(matches('aaaaa', 'aa'), [
    { start: 0, end: 2 },
    { start: 2, end: 4 },
  ]);
  assert.equal(matches('cat '.repeat(2501), 'cat').length, 2501);
  assert.deepEqual(slices('one\ntwo one\ntwo', 'one\ntwo'), ['one\ntwo', 'one\ntwo']);
});
test('replacement uses literal dollar signs and backslashes and preserves text between matches', () => {
  const text = 'Cat / cat / cats';
  assert.equal(
    apply(text, replacement(text, matches(text, 'cat', { wholeWord: true }), '$&\\x')),
    '$&\\x / $&\\x / cats'
  );
  assert.equal(apply(text, replacement(text, matches(text, 'cat'), '')), ' /  / s');
  assert.equal(replacement(text, [], 'value'), null);
});
test('replace all is based on original matches even when replacement contains the query', () => {
  const text = 'cat cat';
  assert.equal(apply(text, replacement(text, matches(text, 'cat'), 'catcat')), 'catcat catcat');
  assert.equal(apply(text, replacement(text, [matches(text, 'cat')[1]], 'dog')), 'cat dog');
});
