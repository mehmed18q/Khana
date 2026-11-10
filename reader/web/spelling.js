/* Background spelling and source-editor menus. Source and undo stay in the textarea. */
(() => {
  'use strict';
  function create({ current, editor, native, enabled, menu, applyEdit, toast }) {
    const container = document.getElementById('editor-container'),
      layer = document.createElement('div'),
      mirror = document.createElement('div');
    layer.className = 'spelling-layer';
    mirror.className = 'spelling-text';
    layer.setAttribute('aria-hidden', 'true');
    layer.hidden = true;
    layer.append(mirror);
    container.append(layer);
    const properties = [
      'font',
      'lineHeight',
      'letterSpacing',
      'padding',
      'tabSize',
      'whiteSpace',
      'overflowWrap',
      'wordBreak',
      'textAlign',
      'unicodeBidi',
    ];
    let timer = 0,
      token = 0,
      snapshot = null,
      words = [],
      misspelled = new Set(),
      pendingMenu = null;
    function clear() {
      CSS.highlights?.delete('reader-spelling');
      layer.hidden = true;
      snapshot = null;
      pendingMenu = null;
      token++;
    }
    function sync() {
      const field = editor();
      if (!field || layer.hidden) return;
      const css = getComputedStyle(field);
      for (const property of properties)
        if (mirror.style[property] !== css[property]) mirror.style[property] = css[property];
      mirror.dir = field.dir;
      mirror.style.width = `${field.clientWidth}px`;
      layer.style.left = `${field.offsetLeft}px`;
      layer.style.top = `${field.offsetTop}px`;
      layer.style.width = `${field.clientWidth}px`;
      layer.style.height = `${field.clientHeight}px`;
      mirror.style.transform = `translate(${-field.scrollLeft}px, ${-field.scrollTop}px)`;
    }
    function draw() {
      if (!snapshot || editor() !== snapshot.field || snapshot.source !== snapshot.field.value)
        return;
      layer.hidden = false;
      mirror.textContent = snapshot.source + '\u200b';
      sync();
      const highlight = new Highlight();
      for (const word of words)
        if (misspelled.has(word.value)) {
          const range = new Range();
          range.setStart(mirror.firstChild, word.start);
          range.setEnd(mirror.firstChild, word.end);
          highlight.add(range);
        }
      CSS.highlights?.set('reader-spelling', highlight);
    }
    function check() {
      const field = editor(),
        doc = current();
      if (
        !enabled() ||
        !field ||
        !doc ||
        !native() ||
        field.hidden ||
        !document.body.classList.contains('editing')
      ) {
        clear();
        return;
      }
      snapshot = { source: field.value, field, id: doc.id, token: ++token };
      words = [
        ...field.value.matchAll(
          /[A-Za-z]+(?:['’][A-Za-z]+)?|[\u0621-\u063a\u0641-\u064a\u066e-\u06d3][\u0621-\u063a\u0640-\u065f\u066e-\u06d3\u200c]*/gu
        ),
      ]
        .filter((match) => match[0].length > 1)
        .map((match) => ({
          value: match[0],
          start: match.index,
          end: match.index + match[0].length,
        }));
      snapshot.remaining = [...new Set(words.map((word) => word.value))];
      misspelled = new Set();
      sendBatch();
    }
    function sendBatch() {
      native()?.checkSpelling(
        snapshot.id,
        snapshot.token,
        JSON.stringify(snapshot.remaining.splice(0, 20000))
      );
    }
    function changed() {
      clearTimeout(timer);
      clear();
      if (enabled()) timer = setTimeout(check, 450);
    }
    function wordAt(event, field) {
      if (!snapshot || snapshot.source !== field.value || layer.hidden) return null;
      // Hit-test the identical mirror without moving the editor's selection.
      field.style.pointerEvents = 'none';
      layer.style.pointerEvents = 'auto';
      const caret = document.caretRangeFromPoint(event.clientX, event.clientY);
      field.style.pointerEvents = '';
      layer.style.pointerEvents = '';
      if (caret?.startContainer !== mirror.firstChild) return null;
      return words.find((word) => word.start <= caret.startOffset && word.end >= caret.startOffset);
    }
    function showMenu(context, suggestions = null) {
      const { event, field, source, start, end, word, id } = context;
      const valid = () =>
        current()?.id === id && editor() === field && field.value === source && !field.readOnly;
      const replace = (a, b, text) => {
        if (valid())
          applyEdit(field, {
            start: a,
            end: b,
            text,
            selectionStart: a + text.length,
            selectionEnd: a + text.length,
          });
      };
      const actions = [];
      if (word && misspelled.has(word.value) && enabled()) {
        if (suggestions === null)
          actions.push({ id: 'checking', label: 'Checking spelling…', disabled: true });
        else if (!suggestions.length)
          actions.push({ id: 'no-suggestions', label: 'No spelling suggestions', disabled: true });
        else
          for (const value of suggestions)
            actions.push({
              id: 'spelling-suggestion',
              label: value,
              translate: false,
              run: () => replace(word.start, word.end, value),
            });
        for (const [everywhere, label] of [
          [false, 'Ignore in this document'],
          [true, 'Ignore in all documents'],
        ])
          actions.push({
            id: everywhere ? 'ignore-all' : 'ignore-document',
            label,
            run: () => {
              if (valid()) {
                native()?.ignoreSpelling(id, word.value, everywhere);
                changed();
              }
            },
          });
        actions.push(null);
      }
      actions.push(
        {
          id: 'undo',
          label: 'Undo',
          disabled: field.readOnly,
          run: () => {
            if (valid()) document.execCommand('undo');
          },
        },
        {
          id: 'redo',
          label: 'Redo',
          disabled: field.readOnly,
          run: () => {
            if (valid()) document.execCommand('redo');
          },
        },
        null,
        {
          id: 'cut',
          label: 'Cut',
          disabled: start === end || field.readOnly,
          run: () => {
            if (valid()) {
              native()?.copyText(source.slice(start, end));
              replace(start, end, '');
            }
          },
        },
        {
          id: 'copy',
          label: 'Copy',
          disabled: start === end,
          run: () => native()?.copyText(source.slice(start, end)),
        },
        {
          id: 'paste',
          label: 'Paste',
          disabled: field.readOnly,
          run: () => native()?.clipboardText((text) => replace(start, end, text)),
        },
        { id: 'select-all', label: 'Select all', run: () => field.select() }
      );
      menu.open(event, field, 'Edit text', actions);
    }
    container.addEventListener('contextmenu', (event) => {
      const field = event.target.closest('.source-editor');
      if (!field) return;
      const context = {
        event,
        field,
        source: field.value,
        start: field.selectionStart,
        end: field.selectionEnd,
        word: wordAt(event, field),
        id: current()?.id,
        token: ++token,
      };
      pendingMenu = context;
      showMenu(context);
      if (context.word && misspelled.has(context.word.value) && enabled())
        native()?.spellingSuggestions(context.id, context.token, context.word.value);
    });
    container.addEventListener('input', changed);
    document.addEventListener('reader-editor-view', changed);
    container.addEventListener('scroll', sync, true);
    new ResizeObserver(sync).observe(container);
    document.fonts.ready.then(sync);
    return {
      changed,
      receive(raw) {
        const result = JSON.parse(raw);
        if (result.kind === 'suggest') {
          if (
            pendingMenu?.token === result.token &&
            current()?.id === result.id &&
            !document.getElementById('file-context-menu').hidden &&
            pendingMenu.field.value === pendingMenu.source
          )
            showMenu(pendingMenu, result.suggestions || []);
          return;
        }
        if (
          !snapshot ||
          result.token !== snapshot.token ||
          result.id !== current()?.id ||
          snapshot.source !== editor()?.value ||
          !enabled()
        )
          return;
        if (result.error) {
          clear();
          toast('Spell check is unavailable.', true);
          return;
        }
        for (const word of result.misspelled) misspelled.add(word);
        if (snapshot.remaining.length) sendBatch();
        else draw();
      },
    };
  }
  window.ReaderSpelling = { create };
})();
