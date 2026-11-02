const { test } = require('node:test');
const assert = require('node:assert/strict');
const { normalize, hash, locate } = require('../reader/web/annotations.js');
const blocks = (texts) =>
  texts.map((text, index) => ({ text, index, hash: hash(text), tag: 'p', heading: 'chapter' }));
const anchor = (text, index = 1) => ({
  text,
  tail: text,
  hash: hash(text),
  tag: 'p',
  index,
  heading: 'chapter',
  before: '',
  after: '',
  quote: '',
});
test('unchanged Persian/English text relocates after preceding content is inserted', () => {
  const text = 'مکان مطالعه English';
  const found = locate(
    blocks(['New heading', 'New paragraph', 'Before', text, 'After']),
    anchor(text)
  );
  assert.equal(found.block.index, 3);
  assert.equal(found.exact, true);
});
test('neighbor context disambiguates repeated paragraphs', () => {
  const a = { ...anchor('Repeated'), before: 'Unique before', after: 'Unique after' };
  assert.equal(
    locate(blocks(['Repeated', 'Unique before', 'Repeated', 'Unique after']), a).block.index,
    2
  );
});
test('selected quote can recover an edited paragraph without claiming an exact match', () => {
  const a = { ...anchor('Old paragraph'), quote: 'selected words' };
  const found = locate(blocks(['Elsewhere', 'New paragraph with selected words']), a);
  assert.equal(found.block.index, 1);
  assert.equal(found.exact, false);
});
test('missing and empty text locations have an explicit fallback', () => {
  assert.equal(locate(blocks(['Only remaining paragraph']), anchor('Gone', 99)).exact, false);
  assert.equal(locate([], anchor('Gone')).block, null);
  assert.equal(normalize('  فارسی\n English  '), 'فارسی English');
});
