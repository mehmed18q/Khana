/* Background spelling and source-editor menus. Source and undo stay in the textarea. */
(() => {
  'use strict';
  function create({ current, editor, native, enabled, menu, applyEdit, toast, lineNumbers }) {
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
      pendingMenu = null,
      paintFrame = 0,
      painted = '';
    function clear() {
      CSS.highlights?.delete('reader-spelling');
      layer.hidden = true;
      snapshot = null;
      pendingMenu = null;
      painted = '';
      cancelAnimationFrame(paintFrame);
      CSS.highlights?.delete('reader-editor-selection');
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
      // The textarea's RTL scrollbar sits on the left. Its text viewport starts
      // after clientLeft (scrollbar plus border), not at the element's edge.
      layer.style.left = `${field.offsetLeft + field.clientLeft}px`;
      layer.style.top = `${field.offsetTop + field.clientTop}px`;
      layer.style.width = `${field.clientWidth}px`;
      layer.style.height = `${field.clientHeight}px`;
      mirror.style.transform = `translate(${-field.scrollLeft}px, ${-field.scrollTop}px)`;
    }
    function draw() {
      if (!snapshot || editor() !== snapshot.field || snapshot.source !== snapshot.field.value)
        return;
      layer.hidden = false;
      if (mirror.textContent !== snapshot.source + '\u200b')
        mirror.textContent = snapshot.source + '\u200b';
      sync();
      const field = snapshot.field,
        metrics = lineNumbers.metrics(field),
        first = Math.max(
          0,
          Math.floor(ReaderScrollSync.interpolate(metrics, field.scrollTop - field.clientHeight, 1))
        ),
        last =
          Math.ceil(
            ReaderScrollSync.interpolate(metrics, field.scrollTop + field.clientHeight * 2, 1)
          ) + 1,
        start = snapshot.lines[first] ?? 0,
        end = snapshot.lines[last] ?? snapshot.source.length,
        key = `${snapshot.token}:${start}:${end}:${misspelled.size}`;
      if (key === painted) return;
      painted = key;
      const highlight = new Highlight();
      // Only visible lines (plus a screen on each side) need painted ranges.
      // Thousands of offscreen ranges make Chromium repaint on every caret move.
      for (let index = wordIndex(start); index < words.length; index++) {
        const word = words[index];
        if (word.start >= end) break;
        if (misspelled.has(word.value)) {
          const range = new Range();
          range.setStart(mirror.firstChild, word.start);
          range.setEnd(mirror.firstChild, word.end);
          highlight.add(range);
        }
      }
      CSS.highlights?.set('reader-spelling', highlight);
    }
    function wordIndex(offset) {
      let low = 0,
        high = words.length;
      while (low < high) {
        const middle = (low + high) >>> 1;
        if (words[middle].end < offset) low = middle + 1;
        else high = middle;
      }
      return low;
    }
    function refresh() {
      sync();
      cancelAnimationFrame(paintFrame);
      paintFrame = requestAnimationFrame(draw);
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
      snapshot.lines = ReaderSourceText.get(field).starts;
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
      if (field.selectionStart !== field.selectionEnd) {
        const word = words[wordIndex(field.selectionStart)];
        return word?.start === field.selectionStart && word.end === field.selectionEnd
          ? word
          : null;
      }
      // Hit-test the few painted errors without changing textarea styles or focus.
      for (const range of CSS.highlights?.get('reader-spelling') || [])
        for (const rect of range.getClientRects())
          if (
            event.clientX >= rect.left &&
            event.clientX <= rect.right &&
            event.clientY >= rect.top &&
            event.clientY <= rect.bottom
          )
            return words[wordIndex(range.startOffset)];
      return null;
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
      menu.open(event, field, 'Edit text', actions, false, () => {
        CSS.highlights?.delete('reader-editor-selection');
        pendingMenu = null;
        if (!snapshot) layer.hidden = true;
      });
      pendingMenu = context;
      if (start !== end) {
        if (mirror.textContent !== source + '\u200b') mirror.textContent = source + '\u200b';
        layer.hidden = false;
        sync();
        const range = new Range();
        range.setStart(mirror.firstChild, start);
        range.setEnd(mirror.firstChild, end);
        CSS.highlights?.set('reader-editor-selection', new Highlight(range));
      }
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
    // Drop old ranges before other input handlers read layout for the new text.
    container.addEventListener('beforeinput', clear, true);
    container.addEventListener('input', changed, true);
    document.addEventListener('reader-editor-view', changed);
    container.addEventListener('scroll', refresh, true);
    new ResizeObserver(refresh).observe(container);
    document.fonts.ready.then(refresh);
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
