const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const insertions = require('../reader/web/insertions.js');
const context = { ReaderInsertions: insertions, module: { exports: {} } };
vm.runInNewContext(
  fs.readFileSync(require.resolve('../reader/web/structures.js'), 'utf8'),
  context
);
const structures = context.module.exports;

test('tables retain escapes, alignments and exact surrounding source ranges', () => {
  const table = '| **Name** | Value |\n| :--- | ---: |\n| a\\|b | ۱۲۳ |';
  const source = 'before\n\n' + table + '\n\nafter';
  const [block] = structures.scan(source, 'Markdown');
  assert.equal(source.slice(block.start, block.end), table);
  assert.equal(block.model.cells[1][0].value, 'a\\|b');
  block.model.cells[0].forEach((cell, i) => {
    cell.alignment = block.model.alignment[i];
  });
  assert.equal(structures.serializeTable(block.model, block.model.cells, 'Markdown'), table);
  block.model.cells[1][1].value = 'new';
  const value =
    source.slice(0, block.start) +
    structures.serializeTable(block.model, block.model.cells, 'Markdown') +
    source.slice(block.end);
  assert.equal(value, source.replace('۱۲۳', 'new'));
});

test('fenced code that resembles a table is never edited as a table', () => {
  const source = '```text\n| a | b |\n| --- | --- |\n| c | d |\n```';
  assert.equal(structures.scan(source, 'Markdown').length, 0);
});

test('generated flowcharts reopen with all nodes, labels, edges and direction', () => {
  const model = {
    direction: 'RL',
    title: 'فرایند',
    nodes: [
      { id: 'N1', shape: 'terminal', label: 'شروع < API' },
      { id: 'N2', shape: 'decision', label: 'بله؟' },
    ],
    edges: [{ from: 'N1', to: 'N2', label: 'A | B' }],
  };
  const source = insertions.flowchart(model);
  const [block] = structures.scan(source, 'Markdown');
  assert.deepEqual(JSON.parse(JSON.stringify(block.model)), model);
  assert.equal(insertions.flowchart(block.model), source);
  assert.equal(structures.parseFlow('flowchart LR\nA --> B'), null);
});
