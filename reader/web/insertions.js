/* Portable source for tables and Mermaid flowcharts. No DOM dependencies. */
(() => {
  'use strict';
  const LIMITS = { rows: 50, columns: 12, nodes: 30, edges: 60 };
  const html = (text) =>
    String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  const oneLine = (value) => String(value).replace(/[\r\n\t]+/g, ' ');
  const markdownCell = (value) => oneLine(value).replace(/\\/g, '\\\\').replace(/\|/g, '\\|');

  function table(headers, rows, format = 'Markdown') {
    if (!Array.isArray(headers) || headers.length < 1 || headers.length > LIMITS.columns)
      throw new Error('Choose between 1 and 12 columns.');
    if (!Array.isArray(rows) || rows.length < 1 || rows.length > LIMITS.rows)
      throw new Error('Choose between 1 and 50 data rows.');
    if (rows.some((row) => !Array.isArray(row) || row.length !== headers.length))
      throw new Error('Every row must have the same number of cells.');
    if ([...headers, ...rows.flat()].some((cell) => typeof cell !== 'string' || cell.length > 2000))
      throw new Error('Table cells must contain text of at most 2,000 characters.');
    if (format === 'HTML') {
      const row = (cells, tag) =>
        `    <tr>${cells.map((cell) => `<${tag}>${html(oneLine(cell))}</${tag}>`).join('')}</tr>`;
      return [
        '<table>',
        '  <thead>',
        row(headers, 'th'),
        '  </thead>',
        '  <tbody>',
        ...rows.map((cells) => row(cells, 'td')),
        '  </tbody>',
        '</table>',
      ].join('\n');
    }
    const row = (cells) => `| ${cells.map(markdownCell).join(' | ')} |`;
    return [row(headers), row(headers.map(() => '---')), ...rows.map(row)].join('\n');
  }

  function label(value) {
    // Mermaid numeric entities keep quotes, delimiters, and HTML in plain labels.
    return oneLine(value).replace(/[#"&<>|`%]/g, (char) => `#${char.codePointAt(0)};`);
  }

  function flowchart(model, format = 'Markdown') {
    const { nodes, edges, direction = 'TD', title = '' } = model;
    if (!['TD', 'LR', 'RL', 'BT'].includes(direction))
      throw new Error('Choose a valid flow direction.');
    if (!Array.isArray(nodes) || !nodes.length || nodes.length > LIMITS.nodes)
      throw new Error('Use between 1 and 30 steps.');
    if (!Array.isArray(edges) || edges.length > LIMITS.edges)
      throw new Error('Use at most 60 connections.');
    if (typeof title !== 'string' || title.length > 150)
      throw new Error('The title must be 150 characters or fewer.');
    const shapes = {
      process: ['["', '"]'],
      terminal: ['(["', '"])'],
      decision: ['{"', '"}'],
      data: ['[/"', '"/]'],
    };
    const ids = new Set();
    const lines = [`flowchart ${direction}`];
    if (title.trim()) lines.push(`  accTitle: ${oneLine(title).trim()}`);
    for (const node of nodes) {
      if (!/^N[1-9]\d*$/.test(node.id) || ids.has(node.id))
        throw new Error('Each step needs a unique ID.');
      if (!shapes[node.shape]) throw new Error('Choose a valid step shape.');
      if (typeof node.label !== 'string' || !node.label.trim() || node.label.length > 120)
        throw new Error('Each step needs a label of 1–120 characters.');
      ids.add(node.id);
      const [open, close] = shapes[node.shape];
      lines.push(`  ${node.id}${open}${label(node.label.trim())}${close}`);
    }
    for (const edge of edges) {
      if (!ids.has(edge.from) || !ids.has(edge.to))
        throw new Error('Every connection must point to an existing step.');
      if (typeof edge.label !== 'string' || edge.label.length > 80)
        throw new Error('Connection labels must be 80 characters or fewer.');
      const caption = edge.label.trim() ? `|"${label(edge.label.trim())}"|` : '';
      lines.push(`  ${edge.from} -->${caption} ${edge.to}`);
    }
    const mermaid = lines.join('\n');
    return format === 'HTML'
      ? `<pre><code class="language-mermaid">${html(mermaid)}</code></pre>`
      : `\`\`\`mermaid\n${mermaid}\n\`\`\``;
  }

  function block(source, start, end, content) {
    const before = source.slice(0, start),
      after = source.slice(end);
    const leading =
      before && !before.endsWith('\n\n') ? (before.endsWith('\n') ? '\n' : '\n\n') : '';
    const trailing =
      after && !after.startsWith('\n\n')
        ? after.startsWith('\n')
          ? '\n'
          : '\n\n'
        : after
          ? ''
          : '\n\n';
    const text = leading + content + trailing;
    return {
      start,
      end,
      text,
      selectionStart: start + text.length,
      selectionEnd: start + text.length,
    };
  }
  const api = { LIMITS, table, flowchart, block };
  if (typeof module !== 'undefined') module.exports = api;
  if (typeof window !== 'undefined') window.ReaderInsertions = api;
})();
