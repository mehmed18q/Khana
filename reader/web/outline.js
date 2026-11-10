/* Heading navigation follows the current section without scrolling the outline. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ article, contentRoot, scroller, current, editor, lineNumbers, syncEnabled }) {
    let entries = [],
      sourceEntries = [],
      active = null,
      documentId = null,
      driver = 'preview',
      caret = false,
      frame = 0;
    const resize = new ResizeObserver(() => refresh());
    const field = () => (current()?.editMode && editor() && !editor().hidden ? editor() : null);

    function refresh(from = driver, useCaret = caret) {
      driver = from;
      caret = useCaret;
      if (!frame) frame = requestAnimationFrame(update);
    }

    function update() {
      frame = 0;
      const source = field();
      if (driver === 'editor' && source && sourceEntries.length) {
        if (current()?.previewPending) return;
        const line = caret
            ? ReaderSourceText.position(ReaderSourceText.get(source), source.selectionStart).line
            : null,
          top = source.scrollTop + parseFloat(getComputedStyle(source).paddingTop) + 1;
        let low = 0,
          high = sourceEntries.length;
        while (low < high) {
          const middle = (low + high) >>> 1,
            entry = sourceEntries[middle];
          if (line !== null ? entry.line <= line : lineNumbers.lineTop(source, entry.line) <= top)
            low = middle + 1;
          else high = middle;
        }
        setActiveHeading(sourceEntries[Math.max(0, low - 1)].id);
        return;
      }
      // Match the heading's scroll margin, which scales with preview zoom.
      const inset = 24 * (parseFloat(getComputedStyle(article).zoom) || 1),
        top = scroller.getBoundingClientRect().top + inset + 1,
        bottom = scroller.scrollHeight - scroller.clientHeight,
        atEnd = bottom > 1 && scroller.scrollTop >= bottom - 1;
      let selected = null;
      for (const entry of entries) {
        if (!entry.target?.getClientRects().length) continue;
        if (!selected || atEnd || entry.target.getBoundingClientRect().top <= top) selected = entry;
      }
      setActiveHeading(selected?.id);
    }

    function navigate(entry) {
      const source = field();
      if (source && entry.line !== null && !current()?.previewPending) {
        let offset = 0;
        for (let i = 0; i < entry.line; i++) {
          const next = source.value.indexOf('\n', offset);
          if (next < 0) break;
          offset = next + 1;
        }
        source.setSelectionRange(offset, offset);
        source.focus({ preventScroll: true });
        source.scrollTo({
          top:
            lineNumbers.lineTop(source, entry.line) -
            parseFloat(getComputedStyle(source).paddingTop),
          behavior: 'instant',
        });
      }
      entry.target?.scrollIntoView({ behavior: source ? 'instant' : 'smooth', block: 'start' });
      setActiveHeading(entry.id);
    }

    function renderOutline(doc) {
      resize.disconnect();
      resize.observe(scroller);
      const root = contentRoot();
      resize.observe(root.host || root);
      const outlineTop = documentId === doc?.id ? $('outline').scrollTop : 0;
      if (documentId !== doc?.id) {
        driver = 'preview';
        caret = false;
      }
      documentId = doc?.id;
      entries = [];
      sourceEntries = [];
      active = null;
      $('outline').replaceChildren();
      const headings =
        doc?.api && !doc.apiSource
          ? doc.api.operations.map((op) => ({
              id: op.id,
              title: `${op.method.toUpperCase()} ${op.path}`,
              level: 2,
            }))
          : doc?.headings || [];
      if (!headings.length) {
        const note = document.createElement('div');
        note.className = 'outline-empty';
        note.textContent = 'No headings in this document.';
        $('outline').append(note);
        return;
      }
      for (const heading of headings) {
        const button = document.createElement('button'),
          title = document.createElement('span'),
          target = root.querySelector(`[id="${CSS.escape(heading.id)}"]`),
          sourceLine = target?.dataset.sourceLine,
          line = /^\d+$/.test(sourceLine || '') ? Number(sourceLine) : null,
          entry = { id: heading.id, target, line, button };
        title.className = 'outline-title';
        title.textContent = heading.title;
        title.dir = 'auto';
        button.append(title);
        if (line !== null) {
          const number = document.createElement('span');
          number.className = 'outline-line';
          number.dir = 'ltr';
          number.textContent = `Ln ${line + 1}`;
          button.title = `${heading.title} · Line ${line + 1}`;
          button.append(number);
        }
        button.dir = 'auto';
        button.dataset.target = heading.id;
        if (heading.level > 2) button.classList.add('nested');
        button.setAttribute('aria-current', 'false');
        button.onclick = () => navigate(entry);
        $('outline').append(button);
        entries.push(entry);
      }
      sourceEntries = entries
        .filter((entry) => entry.line !== null)
        .sort((a, b) => a.line - b.line);
      $('outline').scrollTop = outlineTop;
      refresh();
    }

    function setActiveHeading(id) {
      if (active?.id === id) return;
      active?.button.classList.remove('active');
      active?.button.setAttribute('aria-current', 'false');
      active = entries.find((entry) => entry.id === id);
      active?.button.classList.add('active');
      active?.button.setAttribute('aria-current', 'location');
    }

    scroller.addEventListener('scroll', () => refresh('preview', false), { passive: true });
    document.addEventListener('reader-editor-view', () => refresh('preview', false));
    document.fonts.ready.then(() => refresh());
    return {
      render: renderOutline,
      bind(source) {
        source.addEventListener(
          'scroll',
          () => {
            // A synchronized source scroll may have been caused by the preview.
            if (source === field()) refresh(syncEnabled() ? 'preview' : 'editor', false);
          },
          { passive: true }
        );
        for (const event of ['click', 'keyup', 'select', 'input'])
          source.addEventListener(event, () => {
            if (source === field()) refresh('editor', true);
          });
      },
    };
  }
  window.ReaderOutline = { create };
})();
