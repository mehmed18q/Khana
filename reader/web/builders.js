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
    nextNode,
    tableModel = null,
    activeCell = { row: 1, col: 0 },
    drag = null,
    copiedRow = null;

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
      tr.dataset.row = row;
      const handleCell = element(row ? 'td' : 'th'),
        handle = element('button', 'table-handle', row ? `↕ ${row}` : '#');
      handle.type = 'button';
      handle.draggable = row > 0;
      handle.dataset.moveRow = row;
      handle.title = row ? 'Drag to move row' : 'Header row';
      handle.onclick = () => {
        activeCell = { row, col: 0 };
        grid
          .querySelectorAll('.selected-row')
          .forEach((node) => node.classList.remove('selected-row'));
        tr.classList.add('selected-row');
      };
      handleCell.append(handle);
      tr.append(handleCell);
      for (let col = 0; col < columnCount; col++) {
        const cell = element(row ? 'td' : 'th'),
          input = element('input');
        cells[row][col] ||= ReaderStructures.record('');
        input.value = cells[row][col].value;
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
          cells[row][col].value = input.value;
          error('table');
        };
        if (!row) {
          const handle = element('button', 'table-handle', `↔ ${col + 1}`);
          handle.type = 'button';
          handle.draggable = true;
          handle.dataset.moveCol = col;
          handle.title = 'Drag to move column';
          cell.append(handle);
        }
        cell.append(input);
        cell.dataset.col = col;
        tr.append(cell);
      }
      (row ? body : head).append(tr);
    }
    table.append(head, body);
    $('table-grid').replaceChildren(table);
    $('table-columns').value = columnCount;
    $('table-rows').value = rowCount;
  }
  function focusCell() {
    activeCell.row = Math.max(0, Math.min(rowCount, activeCell.row));
    activeCell.col = Math.max(0, Math.min(columnCount - 1, activeCell.col));
    const field = $('table-grid').querySelector(
      `input[data-row="${activeCell.row}"][data-col="${activeCell.col}"]`
    );
    field?.focus();
    field?.select();
  }
  const grid = $('table-grid');
  grid.addEventListener('focusin', (event) => {
    if (event.target.matches('[data-move-row]'))
      activeCell = { row: Number(event.target.dataset.moveRow), col: 0 };
    if (event.target.matches('input[data-row]')) {
      grid
        .querySelectorAll('.selected-row')
        .forEach((node) => node.classList.remove('selected-row'));
      activeCell = { row: Number(event.target.dataset.row), col: Number(event.target.dataset.col) };
    }
  });
  function move(axis, from, to) {
    if (from === to) return;
    if (axis === 'row') {
      if (!from || !to) return;
      cells.splice(to, 0, cells.splice(from, 1)[0]);
      activeCell.row = to;
    } else {
      for (const row of cells) row.splice(to, 0, row.splice(from, 1)[0]);
      activeCell.col = to;
    }
    drawTable();
    focusCell();
  }
  grid.addEventListener('dragstart', (event) => {
    const handle = event.target.closest('[data-move-row],[data-move-col]');
    if (!handle) return;
    drag = handle.hasAttribute('data-move-row')
      ? { axis: 'row', index: Number(handle.dataset.moveRow) }
      : { axis: 'col', index: Number(handle.dataset.moveCol) };
    event.dataTransfer.setData('application/x-khana-table', JSON.stringify(drag));
    event.dataTransfer.effectAllowed = 'move';
  });
  grid.addEventListener('dragover', (event) => {
    if (drag) {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
    }
  });
  grid.addEventListener('drop', (event) => {
    if (!drag) return;
    event.preventDefault();
    const target = event.target.closest(drag.axis === 'row' ? 'tr[data-row]' : '[data-col]');
    if (target) move(drag.axis, drag.index, Number(target.dataset[drag.axis]));
    drag = null;
  });
  grid.addEventListener('dragend', () => {
    drag = null;
  });
  grid.addEventListener('keydown', (event) => {
    if (
      event.target.matches('[data-move-row]') &&
      (event.ctrlKey || event.metaKey) &&
      !event.altKey
    ) {
      const key = (event.code || event.key).replace(/^Key/, '').toLowerCase();
      if (key === 'c' || key === 'x') {
        event.preventDefault();
        copyRow();
        if (key === 'x') $('table-delete-row').click();
        return;
      }
      if (key === 'v') {
        event.preventDefault();
        $('table-paste-row').click();
        return;
      }
    }
    if (event.isComposing || !event.target.matches('input[data-row]')) return;
    if (event.altKey && event.shiftKey && event.key.startsWith('Arrow')) {
      event.preventDefault();
      const horizontal = ['ArrowLeft', 'ArrowRight'].includes(event.key),
        axis = horizontal ? 'col' : 'row',
        from = activeCell[axis];
      const delta =
        (['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1) *
        (horizontal && getComputedStyle(grid).direction === 'rtl' ? -1 : 1);
      const to = Math.max(
        horizontal ? 0 : 1,
        Math.min(horizontal ? columnCount - 1 : rowCount, from + delta)
      );
      move(axis, from, to);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    const delta = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
      Enter: [1, 0],
    }[event.key];
    if (!delta) return;
    // Horizontal arrows retain text editing until the caret reaches a cell edge.
    const input = event.target,
      selected = input.selectionStart === 0 && input.selectionEnd === input.value.length,
      towardStart =
        event.key === (getComputedStyle(input).direction === 'rtl' ? 'ArrowRight' : 'ArrowLeft');
    if (
      delta[1] &&
      !selected &&
      (towardStart ? input.selectionStart > 0 : input.selectionEnd < input.value.length)
    )
      return;
    event.preventDefault();
    activeCell.row += delta[0];
    activeCell.col += delta[1] * (getComputedStyle(grid).direction === 'rtl' ? -1 : 1);
    focusCell();
  });
  function copyRow(event) {
    copiedRow = Array.from({ length: columnCount }, (_, col) => ({
      ...cells[activeCell.row][col],
    }));
    const text = copiedRow.map((cell) => cell.value).join('\t') + '\n';
    if (event?.clipboardData) {
      event.preventDefault();
      event.clipboardData.setData('text/plain', text);
    } else context.copyText?.(text);
  }
  grid.addEventListener('copy', (event) => {
    if (event.target.matches('[data-move-row]')) copyRow(event);
  });
  $('table-copy-row').onclick = () => copyRow();
  $('table-paste-row').onclick = () => {
    const request = context,
      target = activeCell.row + 1;
    const apply = (value) => {
      if (context !== request || !context) return;
      const ownText = copiedRow?.map((cell) => cell.value).join('\t') + '\n';
      value ||= copiedRow ? ownText : '';
      if (!value) return;
      const rows = value
        .replace(/\r\n?/g, '\n')
        .replace(/\n$/, '')
        .split('\n')
        .map((row) => row.split('\t'));
      const width = Math.max(columnCount, ...rows.map((row) => row.length));
      if (
        rows.length + rowCount > LIMITS.rows ||
        width > LIMITS.columns ||
        rows.some((row) => row.some((cell) => cell.length > 2000))
      ) {
        error(
          'table',
          'Paste is too large. Use at most 12 columns, 50 data rows, and 2,000 characters per cell.'
        );
        return;
      }
      const records =
        value === ownText && copiedRow
          ? [copiedRow.map((cell) => ({ ...cell }))]
          : rows.map((row) => row.map((value) => ReaderStructures.record(value)));
      records.forEach((row) => {
        while (row.length < width) row.push(ReaderStructures.record(''));
      });
      cells.splice(target, 0, ...records);
      rowCount += records.length;
      columnCount = width;
      activeCell.row = target;
      drawTable();
      focusCell();
    };
    if (context.clipboardText) context.clipboardText(apply);
    else apply('');
  };
  $('table-delete-row').onclick = () => {
    if (!activeCell.row || rowCount <= 1) return;
    cells.splice(activeCell.row, 1);
    rowCount--;
    drawTable();
    focusCell();
  };
  $('table-add-row').onclick = () => {
    if (rowCount >= LIMITS.rows) return;
    cells.splice(
      activeCell.row + 1,
      0,
      Array.from({ length: columnCount }, () => ReaderStructures.record(''))
    );
    rowCount++;
    activeCell.row++;
    drawTable();
    focusCell();
  };
  $('table-delete-column').onclick = () => {
    if (columnCount <= 1) return;
    cells.forEach((row) => row.splice(activeCell.col, 1));
    columnCount--;
    drawTable();
    focusCell();
  };
  $('table-add-column').onclick = () => {
    if (columnCount >= LIMITS.columns) return;
    cells.forEach((row) => row.splice(activeCell.col + 1, 0, ReaderStructures.record('')));
    columnCount++;
    activeCell.col++;
    drawTable();
    focusCell();
  };
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
        cells[startRow + r][startCol + c] = ReaderStructures.record(value);
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
      const visible = cells.slice(0, rowCount + 1).map((row) => row.slice(0, columnCount));
      finish(ReaderStructures.serializeTable(tableModel, visible, context.format));
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
      tableModel = options.model || null;
      cells = tableModel?.cells || [];
      if (tableModel?.alignment)
        cells[0].forEach((cell, i) => {
          cell.alignment = tableModel.alignment[i];
        });
      rowCount = cells.length ? cells.length - 1 : 3;
      columnCount = cells[0]?.length || 3;
      activeCell = { row: 1, col: 0 };
      $('table-dialog-title').textContent = $('table-insert').textContent = options.model
        ? 'Save table'
        : 'Insert table';
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
      if (options.model) model = structuredClone(options.model);
      nextNode = Math.max(0, ...model.nodes.map((node) => Number(node.id.slice(1)))) + 1;
      $('flow-title').value = model.title || 'Process flow';
      $('flow-direction').value = model.direction || 'TD';
      $('flow-dialog-title').textContent = $('flow-insert').textContent = options.model
        ? 'Save flowchart'
        : 'Insert flowchart';
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
