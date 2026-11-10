/* Locate editable structures in source; preserve surrounding text and cell markup. */
(() => {
  'use strict';
  function splitRow(line) {
    const cells = [];
    let cell = '',
      slashes = 0;
    const text = line
      .trim()
      .replace(/^\|/, '')
      .replace(/(?<!\\)\|\s*$/, '');
    for (const char of text) {
      if (char === '|' && slashes % 2 === 0) {
        cells.push(cell.trim());
        cell = '';
      } else cell += char;
      slashes = char === '\\' ? slashes + 1 : 0;
    }
    cells.push(cell.trim());
    return cells;
  }
  const record = (value, extra = {}) => ({ value, ...extra });
  function markdownTable(text) {
    const rows = text.split('\n').map(splitRow),
      alignment = rows.splice(1, 1)[0];
    if (rows.length < 2 || rows.some((row) => row.length !== alignment.length)) return null;
    return {
      cells: rows.map((row) => row.map((value) => record(value))),
      alignment,
      markdown: true,
    };
  }
  function htmlTable(text) {
    const document = new DOMParser().parseFromString(text, 'text/html'),
      table = document.querySelector('table');
    if (
      !table ||
      table.querySelector(
        'table, [rowspan]:not([rowspan="1"]), [colspan]:not([colspan="1"]), tfoot, colgroup'
      ) ||
      table.tBodies.length > 1
    )
      return null;
    const rows = [...table.rows];
    if (
      rows.length < 2 ||
      rows[0].querySelector('td') ||
      rows.some((row) => row.cells.length !== rows[0].cells.length)
    )
      return null;
    return {
      template: table,
      cells: rows.map((row) =>
        [...row.cells].map((cell) =>
          record(cell.textContent, { original: cell.textContent, template: cell })
        )
      ),
    };
  }
  function parseFlow(text) {
    const lines = text
      .trim()
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    const direction = /^(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)\s*;?$/.exec(lines.shift())?.[1];
    if (!direction) return null;
    const model = {
      direction: direction === 'TB' ? 'TD' : direction,
      title: '',
      nodes: [],
      edges: [],
    };
    const decode = (value) =>
      value.replace(/#(\d+);/g, (entity, number) =>
        Number(number) <= 0x10ffff ? String.fromCodePoint(Number(number)) : entity
      );
    const shapes = { '["': 'process', '(["': 'terminal', '{"': 'decision', '[/"': 'data' };
    const closings = { '["': '"]', '(["': '"])', '{"': '"}', '[/"': '"/]' };
    for (const line of lines) {
      if (line.startsWith('accTitle:')) {
        model.title = line.slice(9).trim();
        continue;
      }
      const node = /^(N[1-9]\d*)(\(\["|\[\/"|\["|\{")(.*?)("\]\)|"\/\]|"\]|"\})$/.exec(line);
      if (node) {
        if (closings[node[2]] !== node[4]) return null;
        model.nodes.push({ id: node[1], label: decode(node[3]), shape: shapes[node[2]] });
        continue;
      }
      const edge = /^(N[1-9]\d*)\s+-->(?:\|"(.*?)"\|)?\s+(N[1-9]\d*)$/.exec(line);
      if (edge) {
        model.edges.push({ from: edge[1], to: edge[3], label: decode(edge[2] || '') });
        continue;
      }
      // Unsupported Mermaid syntax remains editable as source without conversion loss.
      return null;
    }
    try {
      ReaderInsertions.flowchart(model);
      return model;
    } catch {
      return null;
    }
  }
  function scan(source, format) {
    const result = [];
    if (format === 'Markdown') {
      const lines = source.split('\n');
      let offset = 0;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i],
          fence = /^\s{0,3}(`{3,}|~{3,})(.*)$/.exec(line);
        if (fence) {
          let last = i + 1;
          const close = new RegExp(`^\\s{0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
          while (last < lines.length && !close.test(lines[last])) last++;
          const text = lines.slice(i, Math.min(last + 1, lines.length)).join('\n');
          if (fence[2].trim() === 'mermaid' && last < lines.length) {
            const raw = lines.slice(i + 1, last).join('\n');
            result.push({
              kind: 'flowchart',
              start: offset,
              end: offset + text.length,
              raw,
              model: parseFlow(raw),
            });
          }
          offset += text.length + 1;
          i = last;
          continue;
        }
        if (
          i + 2 < lines.length &&
          line.includes('|') &&
          splitRow(lines[i + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))
        ) {
          let last = i + 2;
          while (last < lines.length && lines[last].trim() && lines[last].includes('|')) last++;
          const raw = lines.slice(i, last).join('\n');
          result.push({
            kind: 'table',
            start: offset,
            end: offset + raw.length,
            raw,
            model: markdownTable(raw),
          });
          offset += raw.length + 1;
          i = last - 1;
          continue;
        }
        offset += line.length + 1;
      }
    } else {
      let depth = 0,
        start = 0;
      const chunks = [];
      for (const match of source.matchAll(
        /<!--[\s\S]*?-->|<(script|style|textarea)\b[^>]*>[\s\S]*?<\/\1\s*>|<\/?table\b[^>]*>|<pre\b[^>]*>\s*<code\b[^>]*class=["'][^"']*\blanguage-mermaid\b[^"']*["'][^>]*>[\s\S]*?<\/code>\s*<\/pre>/gi
      )) {
        if (/^<table\b/i.test(match[0])) {
          if (depth++ === 0) start = match.index;
        } else if (/^<\/table/i.test(match[0]) && depth && --depth === 0) {
          chunks.push({ 0: source.slice(start, match.index + match[0].length), index: start });
        } else if (!depth && /^<pre\b/i.test(match[0])) chunks.push(match);
      }
      for (const match of chunks) {
        const kind = /^<table\b/i.test(match[0]) ? 'table' : 'flowchart';
        const raw =
          kind === 'table'
            ? match[0]
            : new DOMParser().parseFromString(match[0], 'text/html').querySelector('code')
                .textContent;
        result.push({
          kind,
          start: match.index,
          end: match.index + match[0].length,
          raw,
          model: kind === 'table' ? htmlTable(raw) : parseFlow(raw),
        });
      }
    }
    return result;
  }
  function serializeTable(model, cells, format) {
    if (!model)
      return ReaderInsertions.table(
        cells[0].map((cell) => cell.value),
        cells.slice(1).map((row) => row.map((cell) => cell.value)),
        format
      );
    if (model.markdown) {
      const row = (cells) => `| ${cells.join(' | ')} |`;
      const escapePipes = (value) => {
        let result = '',
          slashes = 0;
        for (const char of value.replace(/[\r\n]/g, ' ')) {
          if (char === '|' && slashes % 2 === 0) result += '\\';
          result += char;
          slashes = char === '\\' ? slashes + 1 : 0;
        }
        return result;
      };
      const lines = cells.map((cells) => row(cells.map((cell) => escapePipes(cell.value))));
      lines.splice(1, 0, row(cells[0].map((cell) => cell.alignment || '---')));
      return lines.join('\n');
    }
    const table = model.template.cloneNode(true);
    for (const row of [...table.rows]) row.remove();
    const head = table.tHead || table.createTHead(),
      body = table.tBodies[0] || table.createTBody();
    cells.forEach((row, index) => {
      const tr = (row[0]?.template?.parentElement || document.createElement('tr')).cloneNode(false);
      row.forEach((cell) => {
        const node = cell.template?.cloneNode(true) || document.createElement(index ? 'td' : 'th');
        if (!cell.template || cell.value !== cell.original) node.textContent = cell.value;
        tr.append(node);
      });
      (index ? body : head).append(tr);
    });
    return table.outerHTML;
  }
  const api = { scan, splitRow, parseFlow, serializeTable, record };
  if (typeof window !== 'undefined') window.ReaderStructures = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
