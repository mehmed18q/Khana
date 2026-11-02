const { test } = require('node:test');
const assert = require('node:assert/strict');
const { transform, link } = require('../reader/web/formatting.js');
const apply = (source, operation) =>
  source.slice(0, operation.start) + operation.text + source.slice(operation.end);

test('bold wraps selected Persian and preserves the inner selection', () => {
  const source = 'سلام English',
    op = transform(source, 0, 4, 'bold');
  assert.equal(apply(source, op), '**سلام** English');
  assert.equal(apply(source, op).slice(op.selectionStart, op.selectionEnd), 'سلام');
});
test('bold toggles off whether the text or entire markup is selected', () => {
  assert.equal(apply('**word**', transform('**word**', 2, 6, 'bold')), 'word');
  assert.equal(apply('**word**', transform('**word**', 0, 8, 'bold')), 'word');
});
test('italic can nest with bold without removing bold markers', () => {
  assert.equal(apply('**word**', transform('**word**', 2, 6, 'italic')), '***word***');
  assert.equal(apply('**word**', transform('**word**', 0, 8, 'italic')), '***word***');
});
test('toggling italic on combined bold and italic preserves bold', () => {
  assert.equal(apply('***word***', transform('***word***', 3, 7, 'italic')), '**word**');
  assert.equal(apply('***word***', transform('***word***', 0, 10, 'italic')), '**word**');
});
test('whitespace stays outside emphasis markers', () => {
  assert.equal(apply(' hello ', transform(' hello ', 0, 7, 'bold')), ' **hello** ');
});
test('empty selections insert a selected placeholder', () => {
  const op = transform('', 0, 0, 'italic');
  assert.equal(op.text, '*italic text*');
  assert.equal(op.text.slice(op.selectionStart, op.selectionEnd), 'italic text');
});
test('inline code handles backticks and toggles plain code', () => {
  assert.equal(transform('a`b', 0, 3, 'code').text, '``a`b``');
  assert.equal(transform('`word`', 0, 6, 'code').text, 'word');
});
test('headings replace the existing level and can toggle off', () => {
  assert.equal(apply('# Title\nBody', transform('# Title\nBody', 3, 3, 'h2')), '## Title\nBody');
  assert.equal(apply('## Title', transform('## Title', 4, 4, 'h2')), 'Title');
});
test('multiline lists preserve subsequent unselected lines', () => {
  const source = 'اول\nSecond\nThird';
  assert.equal(apply(source, transform(source, 0, 11, 'bullet')), '- اول\n- Second\nThird');
  assert.equal(apply(source, transform(source, 0, 11, 'numbered')), '1. اول\n2. Second\nThird');
});
test('quote acts on the whole current line and toggles off', () => {
  assert.equal(apply('Hello', transform('Hello', 2, 2, 'quote')), '> Hello');
  assert.equal(apply('> Hello', transform('> Hello', 2, 7, 'quote')), 'Hello');
});
test('code blocks use a fence longer than fences in the source', () => {
  assert.equal(transform('```', 0, 3, 'code-block').text, '````\n```\n````');
});
test('HTML inline formatting inserts and removes tags', () => {
  assert.equal(transform('سلام', 0, 4, 'bold', 'HTML').text, '<strong>سلام</strong>');
  assert.equal(transform('<em>text</em>', 4, 8, 'italic', 'HTML').text, 'text');
});
test('HTML lists contain list items and HTML code escapes source markup', () => {
  assert.equal(
    transform('One\nTwo', 0, 7, 'bullet', 'HTML').text,
    '<ul>\n  <li>One</li>\n  <li>Two</li>\n</ul>'
  );
  assert.equal(
    transform('<b>x</b>', 0, 8, 'code-block', 'HTML').text,
    '<pre><code>&lt;b&gt;x&lt;/b&gt;</code></pre>'
  );
});
test('Markdown links escape brackets and keep parenthesized destinations intact', () => {
  assert.equal(
    link('', 0, 0, '[guide]', 'https://example.com/a(b)').text,
    '[\\[guide\\]](<https://example.com/a(b)>)'
  );
  assert.equal(link('', 0, 0, 'Section', '#section').text, '[Section](<#section>)');
});
test('HTML links escape both the attribute and label', () => {
  assert.equal(
    link('', 0, 0, '<Guide>', 'https://example.com/?a="b"', 'HTML').text,
    '<a href="https://example.com/?a=&quot;b&quot;">&lt;Guide&gt;</a>'
  );
});
test('unsupported schemes and unescaped whitespace are rejected', () => {
  for (const url of [
    'javascript:alert(1)',
    'data:text/html,hi',
    'file:///etc/passwd',
    'hello world',
  ]) {
    assert.throws(() => link('', 0, 0, 'link', url));
  }
});
