const { test } = require('node:test');
const assert = require('node:assert/strict');
const { detectDirection, firstDirection } = require('../reader/web/bidi.js');

test('Persian prose remains RTL when starting with an English product name', () => {
  assert.equal(detectDirection('Markdown یک روش ساده برای نوشتن مستندات است.'), 'rtl');
  assert.equal(detectDirection('Python را نصب کنید و برنامه را اجرا کنید.'), 'rtl');
});
test('English paragraphs stay LTR with an embedded Persian word', () => {
  assert.equal(
    detectDirection('This paragraph is English, even with a word like خوانا inside it.'),
    'ltr'
  );
});
test('Neutral text inherits a useful direction and technical content stays LTR', () => {
  assert.equal(detectDirection('۱۲۳۴'), 'rtl');
  assert.equal(detectDirection('1234', 'ltr'), 'ltr');
  assert.equal(firstDirection('src/components/Reader.tsx'), 'ltr');
  assert.equal(firstDirection('print("سلام")'), 'ltr');
  assert.equal(firstDirection('سلام'), 'rtl');
});
test('A long URL does not decide the direction of Persian prose', () => {
  assert.equal(
    detectDirection('https://example.com/a-very-long-path/to/something نشانی وب است.'),
    'rtl'
  );
});
