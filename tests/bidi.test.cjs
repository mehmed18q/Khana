const { test } = require('node:test');
const assert = require('node:assert/strict');
const { detectDirection, firstDirection, latinRuns } = require('../reader/web/bidi.js');

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
test('Numbers with separators stay one left-to-right run in RTL prose', () => {
  const runs = (text) => latinRuns(text).map((run) => run.text);
  assert.deepEqual(runs('قیمت 1,234,567 تومان'), ['1,234,567']);
  assert.deepEqual(runs('عدد 2,500.75 و 3,14'), ['2,500.75', '3,14']);
  assert.deepEqual(runs('رشد 50% و دمای 25°C'), ['50%', '25°C']);
  assert.deepEqual(runs('مبلغ $1,200 و دمای -5 درجه'), ['$1,200', '-5']);
  assert.deepEqual(runs('Python 3.12, React 18'), ['Python 3.12', 'React 18']);
  assert.deepEqual(runs("نسخهٔ v2.0 don't break"), ["v2.0 don't break"]);
  assert.deepEqual(runs('word-5 a-b'), ['word-5 a-b']);
});
