/* Small, accessible source builders. Text stays data until serialization. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const { LIMITS } = ReaderInsertions;
  let context = null,
    cells = [],
    rowCount = 3,
    columnCount = 3,
    model,
    nextNode;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function error(kind, message = '') {
    const node = $(`${kind}-error`);
    node.textContent = message;
    node.hidden = !message;
  }
  function finish(content) {
    const current = context;
    context = null;
    $(`${current.kind}-dialog`).close();
    current.onInsert(content);
  }
  for (const kind of ['table', 'flow']) {
    $(`${kind}-cancel`).onclick = () => $(`${kind}-dialog`).close();
    $(`${kind}-dialog`).addEventListener('close', () => {
      if ($(`${kind}-dialog`).open) return;
      if (context?.kind !== kind) return;
      const current = context;
      context = null;
      current.onCancel();
    });
  }

  function drawTable() {
    const table = element('table'),
      head = element('thead'),
      body = element('tbody');
    for (let row = 0; row <= rowCount; row++) {
      cells[row] ||= [];
      const tr = element('tr');
      for (let col = 0; col < columnCount; col++) {
        const cell = element(row ? 'td' : 'th'),
          input = element('input');
        input.value = cells[row][col] ?? '';
        input.dir = 'auto';
        input.maxLength = 2000;
        input.dataset.row = row;
        input.dataset.col = col;
        input.placeholder = row ? '' : `Header ${col + 1}`;
        input.setAttribute(
          'aria-label',
          row ? `Row ${row}, column ${col + 1}` : `Header ${col + 1}`
        );
        input.oninput = () => {
          cells[row][col] = input.value;
          error('table');
        };
        cell.append(input);
        tr.append(cell);
      }
      (row ? body : head).append(tr);
    }
    table.append(head, body);
    $('table-grid').replaceChildren(table);
    $('table-columns').value = columnCount;
    $('table-rows').value = rowCount;
  }
  for (const id of ['table-columns', 'table-rows']) {
    $(id).addEventListener('change', () => {
      if (!$('table-columns').checkValidity() || !$('table-rows').checkValidity()) return;
      columnCount = Number($('table-columns').value);
      rowCount = Number($('table-rows').value);
      error('table');
      drawTable();
    });
  }
  $('table-grid').addEventListener('paste', (event) => {
    const input = event.target.closest('input[data-row]');
    const text = event.clipboardData?.getData('text/plain');
    if (!input || !text || !/[\t\r\n]/.test(text)) return;
    event.preventDefault();
    const rows = text
      .replace(/\r\n?/g, '\n')
      .replace(/\n$/, '')
      .split('\n')
      .map((row) => row.split('\t'));
    const startRow = Number(input.dataset.row),
      startCol = Number(input.dataset.col);
    const endRow = startRow + rows.length - 1,
      endCol = startCol + Math.max(...rows.map((row) => row.length));
    if (
      endRow > LIMITS.rows ||
      endCol > LIMITS.columns ||
      rows.some((row) => row.some((cell) => cell.length > 2000))
    ) {
      error(
        'table',
        'Paste is too large. Use at most 12 columns, 50 data rows, and 2,000 characters per cell.'
      );
      return;
    }
    rows.forEach((row, r) => {
      cells[startRow + r] ||= [];
      row.forEach((value, c) => {
        cells[startRow + r][startCol + c] = value;
      });
    });
    rowCount = Math.max(rowCount, endRow);
    columnCount = Math.max(columnCount, endCol);
    error('table');
    drawTable();
    $('table-grid').querySelector(`[data-row="${startRow}"][data-col="${startCol}"]`).focus();
  });
  $('table-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!context) return;
    try {
      const row = (r) => Array.from({ length: columnCount }, (_, c) => cells[r]?.[c] || '');
      finish(
        ReaderInsertions.table(
          row(0),
          Array.from({ length: rowCount }, (_, i) => row(i + 1)),
          context.format
        )
      );
    } catch (exception) {
      error('table', exception.message);
    }
  });

  function removeButton(label, callback) {
    const button = element('button', 'builder-remove', '×');
    button.type = 'button';
    button.title = label;
    button.setAttribute('aria-label', label);
    button.onclick = callback;
    return button;
  }
  function nodeSelect(value, label, callback) {
    const select = element('select');
    select.setAttribute('aria-label', label);
    for (const [index, node] of model.nodes.entries()) {
      const option = element('option', '', `${index + 1}. ${node.label || 'Untitled step'}`);
      option.value = node.id;
      option.dir = 'auto';
      select.append(option);
    }
    select.value = value;
    select.onchange = () => callback(select.value);
    return select;
  }
  function drawEdges() {
    $('flow-edges').replaceChildren();
    if (!model.edges.length)
      $('flow-edges').append(
        element('p', 'empty-connections', 'No connections yet. Add one to link your steps.')
      );
    model.edges.forEach((edge, index) => {
      const row = element('div', 'flow-edge');
      const from = nodeSelect(edge.from, `Connection ${index + 1} from`, (value) => {
        edge.from = value;
      });
      const to = nodeSelect(edge.to, `Connection ${index + 1} to`, (value) => {
        edge.to = value;
      });
      const label = element('input');
      label.value = edge.label;
      label.placeholder = 'Label (optional)';
      label.dir = 'auto';
      label.maxLength = 80;
      label.setAttribute('aria-label', `Connection ${index + 1} label`);
      label.oninput = () => {
        edge.label = label.value;
      };
      row.append(
        from,
        element('span', 'flow-edge-arrow', '→'),
        to,
        label,
        removeButton(`Remove connection ${index + 1}`, () => {
          model.edges.splice(index, 1);
          drawEdges();
        })
      );
      $('flow-edges').append(row);
    });
    $('flow-add-edge').disabled = model.edges.length >= LIMITS.edges;
  }
  function drawNodes() {
    $('flow-nodes').replaceChildren();
    model.nodes.forEach((node, index) => {
      const row = element('div', 'flow-node');
      row.dataset.id = node.id;
      const input = element('input');
      input.value = node.label;
      input.placeholder = 'Step label';
      input.dir = 'auto';
      input.maxLength = 120;
      input.required = true;
      input.setAttribute('aria-label', `Step ${index + 1} label`);
      input.oninput = () => {
        node.label = input.value;
        error('flow');
        drawEdges();
      };
      const shape = element('select');
      shape.setAttribute('aria-label', `Step ${index + 1} shape`);
      for (const [value, title] of Object.entries({
        process: 'Process',
        terminal: 'Start / End',
        decision: 'Decision',
        data: 'Input / Output',
      })) {
        const option = element('option', '', title);
        option.value = value;
        shape.append(option);
      }
      shape.value = node.shape;
      shape.onchange = () => {
        node.shape = shape.value;
      };
      const remove = removeButton(`Remove step ${index + 1}`, () => {
        model.nodes.splice(index, 1);
        model.edges = model.edges.filter((edge) => edge.from !== node.id && edge.to !== node.id);
        drawNodes();
        drawEdges();
      });
      remove.disabled = model.nodes.length === 1;
      row.append(element('span', 'step-number', String(index + 1)), input, shape, remove);
      $('flow-nodes').append(row);
    });
    $('flow-add-node').disabled = model.nodes.length >= LIMITS.nodes;
  }
  $('flow-add-node').onclick = () => {
    if (model.nodes.length >= LIMITS.nodes) return;
    model.nodes.push({ id: `N${nextNode++}`, label: '', shape: 'process' });
    drawNodes();
    drawEdges();
    $('flow-nodes').lastElementChild.querySelector('input').focus();
  };
  $('flow-add-edge').onclick = () => {
    if (model.edges.length >= LIMITS.edges) return;
    model.edges.push({ from: model.nodes[0].id, to: model.nodes.at(-1).id, label: '' });
    drawEdges();
    $('flow-edges').lastElementChild.querySelector('select').focus();
  };
  $('flow-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!context) return;
    try {
      model.title = $('flow-title').value;
      model.direction = $('flow-direction').value;
      finish(ReaderInsertions.flowchart(model, context.format));
    } catch (exception) {
      error('flow', exception.message);
    }
  });

  function open(kind, options) {
    if (context || document.querySelector('dialog[open]')) return;
    kind = kind === 'flowchart' ? 'flow' : kind;
    context = { ...options, kind };
    error(kind);
    if (kind === 'table') {
      cells = [];
      rowCount = 3;
      columnCount = 3;
      drawTable();
    } else {
      nextNode = 4;
      model = {
        nodes: [
          { id: 'N1', label: 'Start', shape: 'terminal' },
          { id: 'N2', label: 'Step', shape: 'process' },
          { id: 'N3', label: 'End', shape: 'terminal' },
        ],
        edges: [
          { from: 'N1', to: 'N2', label: '' },
          { from: 'N2', to: 'N3', label: '' },
        ],
      };
      $('flow-title').value = 'Process flow';
      $('flow-direction').value = 'TD';
      drawNodes();
      drawEdges();
    }
    $(`${kind}-dialog`).showModal();
    (kind === 'table'
      ? $('table-grid').querySelector('input')
      : $('flow-nodes').querySelector('input')
    ).focus();
  }
  window.ReaderBuilders = { open };
})();
