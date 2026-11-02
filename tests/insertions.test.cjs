const { test } = require('node:test');
const assert = require('node:assert/strict');
const { table, flowchart, block } = require('../reader/web/insertions.js');
const model = () => ({
  title: 'ثبت سفارش Order',
  direction: 'RL',
  nodes: [
    { id: 'N1', label: 'شروع', shape: 'terminal' },
    { id: 'N2', label: 'Ready?', shape: 'decision' },
    { id: 'N3', label: 'ثبت داده', shape: 'data' },
  ],
  edges: [
    { from: 'N1', to: 'N2', label: '' },
    { from: 'N2', to: 'N3', label: 'بله Yes' },
    { from: 'N2', to: 'N1', label: 'No' },
  ],
});
test('table preserves mixed text and escapes separators and backslashes', () => {
  assert.equal(
    table(['نام', 'Path'], [['الف | ب', 'C:\\temp\nnext']]),
    '| نام | Path |\n| --- | --- |\n| الف \\| ب | C:\\\\temp next |'
  );
});
test('HTML tables escape literal cell contents', () => {
  const source = table(['Name'], [['<script>"x" & y</script>']], 'HTML');
  assert.match(source, /<thead>/);
  assert.match(source, /<tbody>/);
  assert.match(source, /&lt;script&gt;&quot;x&quot; &amp; y&lt;\/script&gt;/);
  assert.doesNotMatch(source, /<script>/);
});
test('table bounds and inconsistent rows are rejected', () => {
  assert.throws(() => table([], [[]]));
  assert.throws(() => table(Array(13).fill(''), []));
  assert.throws(() => table(['A'], []));
  assert.throws(() => table(['A'], Array(51).fill([''])));
  assert.throws(() => table(['A'], [['one', 'two']]));
  assert.throws(() => table(['A'], [['x'.repeat(2001)]]));
});
test('flowchart emits standard source, Persian labels, decisions, and a loop', () => {
  const source = flowchart(model());
  assert.ok(source.startsWith('```mermaid\nflowchart RL\n'));
  assert.match(source, /N1\(\["شروع"\]\)/);
  assert.match(source, /N2\{"Ready\?"\}/);
  assert.ok(source.includes('N3[/"ثبت داده"/]'));
  assert.ok(source.includes('N2 -->|"بله Yes"| N3'));
  assert.ok(source.includes('N2 -->|"No"| N1'));
});
test('syntax characters stay inside labels', () => {
  const graph = model();
  graph.nodes[0].label = '" ] --> Evil[<script> & # % ` |';
  const source = flowchart(graph);
  assert.match(source, /#34;/);
  assert.match(source, /#60;script#62;/);
  assert.doesNotMatch(source, /<script>/);
});
test('HTML flowcharts keep an escaped Mermaid code block', () => {
  const source = flowchart(model(), 'HTML');
  assert.ok(source.startsWith('<pre><code class="language-mermaid">flowchart RL'));
  assert.match(source, /--&gt;/);
  assert.ok(source.endsWith('</code></pre>'));
});
test('flowchart validates identities, connections, shapes, labels and bounds', () => {
  for (const change of [
    (g) => {
      g.nodes[0].id = 'A --> B';
    },
    (g) => {
      g.nodes[1].id = 'N1';
    },
    (g) => {
      g.nodes[0].label = ' ';
    },
    (g) => {
      g.nodes[0].shape = 'script';
    },
    (g) => {
      g.edges[0].to = 'N99';
    },
    (g) => {
      g.edges = Array(61).fill(g.edges[0]);
    },
    (g) => {
      g.direction = 'wrong';
    },
  ]) {
    const graph = model();
    change(graph);
    assert.throws(() => flowchart(graph));
  }
});
test('blocks replace the selection and keep neighboring prose separate', () => {
  const source = 'Before selected after',
    op = block(source, 7, 15, 'TABLE');
  assert.equal(
    source.slice(0, op.start) + op.text + source.slice(op.end),
    'Before \n\nTABLE\n\n after'
  );
  assert.equal(op.selectionStart, op.selectionEnd);
  assert.equal(block('Before\n\n', 8, 8, 'TABLE').text, 'TABLE\n\n');
});
