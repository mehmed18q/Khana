(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const formatNumber = number => new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(number);
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const defaults = { theme: 'light', direction: 'smart', fontSize: 17, lineHeight: 2, wide: false, syncScroll: true, previewZoom: 100 };
  let settings = { ...defaults }, bridge, activeId = null, observer, toastTimer, searchTimer;
  const documents = new Map(), positions = new Map(), overrides = new Map();
  const editors = new Map(), previewTimers = new Map();
  const article = $('document'), scroller = $('reading-scroll');
  let results = [], resultIndex = -1;
  let linkContext = null;
  const reading = ReaderLibrary.create({ article, scroller, current: () => documents.get(activeId),
    documents, sourceOf, native: () => bridge, toast });
  const sync = ReaderScrollSync.create({ article, scroller, current: () => documents.get(activeId),
    editor: () => editors.get(activeId), enabled: () => settings.syncScroll });
  const zoom = ReaderPreviewZoom.create({ article, scroller, beforeChange: () => sync.reset(),
    afterChange: () => { sync.mount('preview'); updateProgress(); },
    changed: value => { settings.previewZoom = value; bridge?.saveSettings(JSON.stringify(settings)); } });
  const supportsFormatting = doc => ['Markdown', 'HTML', 'Word'].includes(doc?.format);
  const supportsBeautify = doc => ['JSON', 'YAML', 'XML'].includes(doc?.format);
  const pdf = ReaderPDF.create({ article, scroller, current: () => documents.get(activeId), native: () => bridge, toast,
    changed: source => { const doc = documents.get(activeId); doc.source = source; updateCaption(); renderFiles(); schedulePreview(doc); } });
  const contentRoot = () => ReaderOpenAPI.contentRoot(article);
  const apiRequests = ReaderApiRequests.create(() => bridge);
  const api = ReaderOpenAPI.create({ article, current: () => documents.get(activeId),
    requests: apiRequests,
    theme: () => settings.theme, direction: () => settings.direction, openLink: href => bridge?.openLink(href, activeId),
    ready: (doc, first) => { reading.mount(); renderOutline(doc);
      if (first) {
        scroller.scrollTo({ top: doc.apiScroll || 0, behavior: 'instant' });
        reading.changed(!positions.has(doc.id));
        sync.mount(doc.editMode ? 'editor' : 'preview');
      }
      if (!$('search-panel').hidden) search(); } });

  function toast(message, error = false) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').classList.toggle('error', error);
    $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 6500 : 2800);
  }

  function preferences(save = true) {
    document.body.dataset.theme = settings.theme;
    document.documentElement.style.setProperty('--font-size', `${settings.fontSize}px`);
    document.documentElement.style.setProperty('--line-height', settings.lineHeight);
    document.documentElement.style.setProperty('--paper-width', settings.wide ? '1100px' : '860px');
    $('font-size').value = settings.fontSize;
    $('font-value').textContent = formatNumber(settings.fontSize);
    $('line-height').value = settings.lineHeight;
    $('line-value').textContent = formatNumber(settings.lineHeight);
    $('wide-page').checked = settings.wide;
    $('sync-scroll').checked = settings.syncScroll;
    zoom.restore(settings.previewZoom);
    $('theme-button').innerHTML = icon(settings.theme === 'dark' ? 'sun' : 'moon');
    $('theme-button').setAttribute('aria-label', settings.theme === 'dark' ? 'Light theme' : 'Dark theme');
    document.querySelectorAll('button[data-direction]').forEach(button => {
      const selected = button.dataset.direction === settings.direction;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    ReaderBidi.apply(article, settings.direction, overrides.get(activeId));
    api.preferences();
    ReaderDiagrams.refreshTheme(article, settings.theme);
    $('direction-status').textContent = { smart: 'Smart direction is on', rtl: 'Right-to-left text', ltr: 'Left-to-right text' }[settings.direction];
    if (save) bridge?.saveSettings(JSON.stringify(settings));
    requestAnimationFrame(updateProgress);
  }

  function renderFiles() {
    $('file-list').replaceChildren();
    $('file-count').textContent = formatNumber(documents.size);
    for (const doc of documents.values()) {
      const row = document.createElement('div');
      row.className = `file-item${doc.id === activeId ? ' active' : ''}`;
      const select = document.createElement('button');
      select.className = 'file-select';
      select.title = doc.path;
      select.innerHTML = icon('file');
      select.setAttribute('aria-current', doc.id === activeId ? 'page' : 'false');
      const name = document.createElement('span');
      name.dir = 'auto'; name.textContent = doc.name;
      select.append(name);
      if (doc.dirty) {
        const dot = document.createElement('span'); dot.className = 'file-dirty';
        dot.title = 'Unsaved changes'; dot.setAttribute('aria-label', 'Unsaved changes');
        select.append(dot);
      }
      select.onclick = () => showDocument(doc.id);
      const close = document.createElement('button');
      close.className = 'file-close'; close.innerHTML = icon('close');
      close.setAttribute('aria-label', `Close ${doc.name}`);
      close.onclick = () => closeDocument(doc.id);
      row.append(select, close);
      $('file-list').append(row);
    }
  }

  function closeDocument(id) {
    const doc = documents.get(id);
    if (!doc || doc.closing) return;
    if (bridge) {
      doc.closing = true;
      bridge.closeFile(id, sourceOf(doc), () => { doc.closing = false; });
    } else removeDocument(id);
  }

  function removeDocument(id) {
    const keys = [...documents.keys()];
    const index = keys.indexOf(id);
    documents.delete(id); positions.delete(id); overrides.delete(id);
    clearTimeout(previewTimers.get(id)); previewTimers.delete(id);
    editors.get(id)?.remove(); editors.delete(id);
    if (activeId === id) {
      activeId = null;
      const remaining = [...documents.keys()];
      showDocument(remaining[Math.min(index, remaining.length - 1)] || null);
    } else { renderFiles(); reading.refresh(); }
  }

  function renderOutline(doc) {
    observer?.disconnect();
    $('outline').replaceChildren();
    const headings = doc?.api && !doc.apiSource ? doc.api.operations.map(op => ({ id: op.id, title: `${op.method.toUpperCase()} ${op.path}`, level: 2 })) : doc?.headings || [];
    if (!headings.length) {
      const note = document.createElement('div');
      note.className = 'outline-empty'; note.textContent = 'No headings in this document.';
      $('outline').append(note); return;
    }
    for (const heading of headings) {
      const button = document.createElement('button');
      button.textContent = heading.title; button.dir = 'auto';
      button.dataset.target = heading.id;
      if (heading.level > 2) button.classList.add('nested');
      button.onclick = () => {
        contentRoot().querySelector(`[id="${CSS.escape(heading.id)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setActiveHeading(heading.id);
      };
      $('outline').append(button);
    }
    observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting);
      if (visible.length) setActiveHeading(visible[0].target.id);
    }, { root: scroller, rootMargin: '0px 0px -65% 0px', threshold: 0 });
    contentRoot().querySelectorAll('h1,h2,h3,h4,h5,h6,[data-api-operation]').forEach(heading => observer.observe(heading));
    setActiveHeading(headings[0].id);
  }

  function setActiveHeading(id) {
    $('outline').querySelectorAll('button').forEach(button => {
      const selected = button.dataset.target === id;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-current', selected ? 'location' : 'false');
    });
  }

  function enhanceDocument() {
    ReaderBidi.prepare(article);
    // Keep direction controls out of nested list items and table cells: their
    // parent paragraph/table can be adjusted using the global direction control.
    article.querySelectorAll('h1,h2,h3,h4,h5,h6,p').forEach(block => {
      if (block.closest('li,th,td')) return;
      const button = document.createElement('button');
      button.className = 'block-direction'; button.innerHTML = icon('direction');
      button.title = 'Change this block: automatic → right to left → left to right';
      button.setAttribute('aria-label', 'Change this block’s direction');
      button.onclick = () => {
        const values = overrides.get(activeId) || {};
        const key = block.dataset.block;
        const next = values[key] === 'rtl' ? 'ltr' : values[key] === 'ltr' ? null : 'rtl';
        if (next) values[key] = next; else delete values[key];
        overrides.set(activeId, values);
        ReaderBidi.apply(article, settings.direction, values);
        toast(next === 'rtl' ? 'This block: right to left' : next === 'ltr' ? 'This block: left to right' : 'This block follows the document direction');
      };
      block.append(button);
    });
    article.querySelectorAll('pre').forEach(pre => {
      const code = pre.querySelector('code');
      if (!code) return;
      const bar = document.createElement('div'); bar.className = 'code-toolbar';
      const label = document.createElement('span'); label.className = 'code-language';
      label.textContent = [...code.classList].find(name => name.startsWith('language-'))?.slice(9) || 'plain text';
      const copy = document.createElement('button'); copy.className = 'copy-code';
      copy.innerHTML = icon('copy') + 'Copy code';
      copy.onclick = () => { bridge?.copyText(code.textContent); toast('Code copied'); };
      bar.append(label, copy); pre.prepend(bar);
    });
    article.querySelectorAll('table').forEach(table => {
      const wrapper = document.createElement('div'); wrapper.className = 'table-scroll';
      table.before(wrapper); wrapper.append(table);
    });
    article.querySelectorAll('a').forEach(link => {
      link.onclick = event => {
        event.preventDefault();
        const href = link.getAttribute('href') || '';
        if (href.startsWith('#')) {
          try { document.getElementById(decodeURIComponent(href.slice(1)))?.scrollIntoView({ behavior: 'smooth' }); } catch { /* Invalid fragment. */ }
        } else bridge?.openLink(href, activeId);
      };
    });
    ReaderDiagrams.mount(article, { theme: settings.theme, copy: source => { bridge?.copyText(source); toast('Diagram source copied'); } });
  }

  function paintPreview(doc) {
    sync.reset();
    api.dispose();
    const top = scroller.scrollTop;
    clearHighlights();
    article.innerHTML = doc?.html || '';
    article.classList.toggle('pdf-document', doc?.format === 'PDF');
    const apiView = Boolean(doc?.api && !doc.apiSource);
    if (doc) { doc.apiRendering = apiView; doc.apiScroll = top; }
    article.classList.toggle('openapi-document', apiView);
    $('api-preview-controls').hidden = !doc?.api;
    $('api-preview-swagger').setAttribute('aria-pressed', String(apiView));
    $('api-preview-source').setAttribute('aria-pressed', String(!apiView));
    article.hidden = !doc;
    $('empty-state').hidden = Boolean(doc);
    $('paper-end').hidden = !doc;
    document.querySelector('.paper-topline').hidden = !doc;
    $('word-count').textContent = `${formatNumber(doc?.words || 0)} words`;
    $('encoding').textContent = doc?.encoding || '—';
    $('document-format').textContent = doc?.format || '—';
    $('reading-time').textContent = doc?.words ? `${formatNumber(Math.max(1, Math.ceil(doc.words / 200)))} min read` : 'Empty document';
    if (doc) {
      if (!doc.html.trim()) article.innerHTML = '<p class="empty-document">This file is empty.</p>';
      if (apiView) api.show(doc);
      else enhanceDocument();
    }
    reading.mount();
    pdf.mount();
    renderOutline(doc); preferences(false);
    scroller.scrollTo({ top, behavior: 'instant' });
    if (!$('search-panel').hidden) search();
    requestAnimationFrame(updateProgress);
  }

  function showDocument(id, refresh = false) {
    if (activeId && documents.has(activeId)) positions.set(activeId, scroller.scrollTop);
    activeId = id;
    const doc = documents.get(id);
    paintPreview(doc);
    showEditor(doc);
    updateCaption(); renderFiles();
    const target = refresh ? Math.min(positions.get(id) || 0, scroller.scrollHeight) : positions.get(id) || 0;
    if (doc?.apiRendering) doc.apiScroll = target;
    scroller.scrollTo({ top: target, behavior: 'instant' });
    reading.changed(!positions.has(id));
    sync.mount('preview');
    if (id) bridge?.activateDocument(id);
    if (!$('search-panel').hidden) search();
    requestAnimationFrame(updateProgress);
  }

  function receiveDocument(payload) {
    const doc = JSON.parse(payload);
    const previous = documents.get(doc.id);
    const refreshing = Boolean(previous);
    if (refreshing) overrides.delete(doc.id);
    clearTimeout(previewTimers.get(doc.id)); previewTimers.delete(doc.id);
    editors.get(doc.id)?.remove(); editors.delete(doc.id);
    doc.editMode = previous?.editMode ?? !doc.path;
    doc.apiSource = previous?.apiSource || false;
    doc.editorDirection = previous?.editorDirection || (doc.format === 'Markdown' ? 'auto' : 'ltr');
    doc.revision = (previous?.revision || 0) + 1;
    doc.savedSource = doc.savedSource ?? doc.source;
    doc.dirty = doc.source !== doc.savedSource;
    documents.set(doc.id, doc);
    showDocument(doc.id, refreshing);
    if (!doc.path) editors.get(doc.id)?.focus();
  }

  function sourceOf(doc) { return editors.get(doc.id)?.value ?? doc.source; }

  function updateCaption() {
    const doc = documents.get(activeId);
    if (doc) doc.dirty = sourceOf(doc) !== doc.savedSource;
    $('current-filename').textContent = doc?.name || 'Khana';
    $('current-filename').title = doc?.path || 'Not saved to disk';
    $('sample-badge').hidden = !doc?.sample;
    $('reload-button').disabled = !doc?.path;
    $('save-button').disabled = $('save-as-button').disabled = !doc || Boolean(doc?.saving);
    $('read-mode').disabled = !doc;
    $('edit-mode').disabled = !doc || (doc.format === 'PDF' && !article.querySelector('[data-editable=true]'));
    $('save-status').textContent = !doc ? 'No document' : doc.saving ? 'Saving…' : doc.dirty ? 'Unsaved changes' : !doc.path ? 'Not saved yet' : 'Saved';
    $('save-status').classList.toggle('dirty', Boolean(doc?.dirty));
    $('editor-name').textContent = doc?.format === 'Word' ? 'Word source (HTML)' : `${doc?.format || 'Document'} source`;
    $('document-format').textContent = doc?.format || '—';
    $('encoding').textContent = doc?.encoding || '—';
    $('beautify-button').disabled = Boolean(doc?.formatting);
    $('beautify-button').textContent = doc?.formatting ? 'Formatting…' : 'Format document';
    bridge?.setDocumentTitle(doc ? `${doc.dirty ? '● ' : ''}${doc.name}` : '');
    reading.refresh();
  }

  function ensureEditor(doc) {
    if (editors.has(doc.id)) return editors.get(doc.id);
    const editor = document.createElement('textarea');
    editor.className = 'source-editor'; editor.value = doc.source;
    editor.spellcheck = false; editor.setAttribute('autocapitalize', 'off');
    editor.setAttribute('autocomplete', 'off'); editor.setAttribute('aria-label', `${doc.format} source editor`);
    editor.placeholder = ['HTML', 'Word'].includes(doc.format) ? '<h1>Your next idea</h1>\n<p>Start writing…</p>' : doc.format === 'Markdown' ? '# Your next idea\n\nStart writing in any language…' : `Start writing ${doc.format}…`;
    editor.addEventListener('input', () => {
      doc.source = editor.value;
      const wasDirty = doc.dirty;
      doc.dirty = doc.source !== doc.savedSource;
      updateCaption(); updateCursor();
      if (wasDirty !== doc.dirty) renderFiles();
      schedulePreview(doc);
    });
    editor.addEventListener('compositionend', () => schedulePreview(doc));
    editor.addEventListener('keydown', event => {
      if (!supportsFormatting(doc) || !(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing) return;
      const key = event.code || event.key.toLowerCase();
      const action = event.shiftKey
        ? ({ KeyX: 'strike', x: 'strike' })[key]
        : ({ KeyB: 'bold', b: 'bold', KeyI: 'italic', i: 'italic', KeyK: 'link', k: 'link', Backquote: 'code', '`': 'code' })[key];
      if (action) { event.preventDefault(); event.stopPropagation(); formatSelection(action); }
    });
    editor.addEventListener('keyup', updateCursor);
    editor.addEventListener('click', updateCursor);
    editor.addEventListener('select', updateCursor);
    editors.set(doc.id, editor); $('editor-container').append(editor);
    sync.bind(editor);
    return editor;
  }

  function showEditor(doc) {
    const enabled = Boolean(doc?.editMode);
    document.body.classList.toggle('editing', enabled);
    $('mode-label').textContent = enabled ? 'Writing mode' : 'Reading mode';
    $('direction-label').textContent = enabled ? 'Preview direction' : 'Text direction';
    $('editor-pane').hidden = !enabled || doc?.format === 'PDF';
    $('format-toolbar').hidden = !supportsFormatting(doc);
    $('beautify-button').hidden = !enabled || !supportsBeautify(doc);
    $('word-editing-note').hidden = doc?.format !== 'Word';
    $('sync-control').hidden = !enabled || doc?.format === 'PDF';
    $('read-mode').classList.toggle('active', !enabled);
    $('edit-mode').classList.toggle('active', enabled);
    $('read-mode').setAttribute('aria-pressed', String(!enabled));
    $('edit-mode').setAttribute('aria-pressed', String(enabled));
    for (const [id, editor] of editors) editor.hidden = id !== doc?.id;
    if (enabled && doc?.format !== 'PDF') {
      const editor = ensureEditor(doc); editor.hidden = false;
      editor.dir = doc.editorDirection; editor.dataset.direction = doc.editorDirection;
      $('editor-direction').value = doc.editorDirection;
    }
    $('preview-status').textContent = doc?.previewPending ? 'Updating preview…' : 'Live preview';
    updateCursor();
    document.body.classList.toggle('editing-pdf', enabled && doc?.format === 'PDF');
  }

  function setEditMode(enabled) {
    const doc = documents.get(activeId);
    if (!doc) return;
    doc.editMode = enabled; showEditor(doc);
    if (enabled) editors.get(doc.id)?.focus({ preventScroll: true });
    sync.mount('preview');
    requestAnimationFrame(updateProgress);
  }

  function updateCursor() {
    const editor = editors.get(activeId);
    if (!editor) return;
    const before = editor.value.slice(0, editor.selectionStart).split('\n');
    $('cursor-position').textContent = `Ln ${before.length}, Col ${[...before.at(-1)].length + 1}`;
  }

  function schedulePreview(doc, delay = 300) {
    clearTimeout(previewTimers.get(doc.id));
    doc.revision++; doc.previewPending = true;
    if (activeId === doc.id) $('preview-status').textContent = 'Updating preview…';
    previewTimers.set(doc.id, setTimeout(() => {
      previewTimers.delete(doc.id);
      if (documents.has(doc.id)) bridge?.previewDocument(doc.id, sourceOf(doc), doc.revision);
    }, delay));
  }

  function receivePreview(payload) {
    const preview = JSON.parse(payload), doc = documents.get(preview.id);
    if (!doc || preview.revision !== doc.revision) return;
    Object.assign(doc, { html: preview.html, headings: preview.headings, words: preview.words, api: preview.api || null, previewPending: false });
    overrides.delete(doc.id);
    if (activeId === doc.id) {
      paintPreview(doc);
      sync.preview();
      $('preview-status').textContent = 'Live preview';
    }
  }

  function receiveSaved(payload) {
    const saved = JSON.parse(payload), doc = documents.get(saved.id);
    if (!doc) return;
    for (const key of ['path', 'name', 'size', 'fingerprint', 'sample', 'format', 'encoding', 'codec', 'bom', 'newline', 'savedSource']) doc[key] = saved[key];
    doc.source = sourceOf(doc); doc.dirty = doc.source !== doc.savedSource;
    updateCaption(); renderFiles(); schedulePreview(doc, 0);
    toast(`Saved ${doc.name}`);
  }

  function saveDocument(saveAs = false) {
    const doc = documents.get(activeId);
    if (!doc || doc.saving) return;
    doc.saving = true; updateCaption();
    bridge?.saveDocument(doc.id, sourceOf(doc), saveAs, () => { doc.saving = false; updateCaption(); });
  }

  function applySourceEdit(editor, operation) {
    if (!operation || editor.readOnly) return false;
    editor.focus();
    editor.setSelectionRange(operation.start, operation.end);
    // Chromium's insertText editing command keeps the textarea's undo history.
    // Assigning .value or setRangeText here would break undo for toolbar edits.
    if (!document.execCommand('insertText', false, operation.text)) {
      toast('Could not apply formatting. Select the source text and try again.', true);
      return false;
    }
    editor.setSelectionRange(operation.selectionStart, operation.selectionEnd);
    // Some engine versions omit input for editing commands; synchronize only
    // when the event did not already update the source buffer.
    const doc = documents.get(activeId);
    if (doc && doc.source !== editor.value) editor.dispatchEvent(new Event('input', { bubbles: true }));
    updateCursor();
    return true;
  }

  function beautifyDocument() {
    const doc = documents.get(activeId), editor = editors.get(activeId);
    if (!bridge || !doc?.editMode || !supportsBeautify(doc) || !editor || editor.readOnly || doc.formatting) return;
    doc.formatting = { editor, source: editor.value, start: editor.selectionStart, end: editor.selectionEnd, top: editor.scrollTop };
    updateCaption();
    bridge.formatSource(doc.id, editor.value);
  }

  function receiveSourceFormatted(raw) {
    const result = JSON.parse(raw), doc = documents.get(result.id), context = doc?.formatting;
    if (!context) return;
    doc.formatting = null;
    updateCaption();
    if (activeId !== result.id || !doc.editMode) return;
    if (context.editor !== editors.get(result.id) || context.editor.value !== context.source) {
      toast('The source changed while formatting. Try Format document again.', true); return;
    }
    if (result.error) { toast(result.error, true); return; }
    if (result.source === context.source) { toast('The document is already formatted.'); return; }
    if (applySourceEdit(context.editor, { start: 0, end: context.source.length, text: result.source,
      selectionStart: Math.min(context.start, result.source.length), selectionEnd: Math.min(context.end, result.source.length) })) {
      context.editor.scrollTop = context.top;
      toast('Document formatted. Ctrl+Z to undo; Save to write changes.');
    }
  }

  function formatSelection(action) {
    const doc = documents.get(activeId), editor = editors.get(activeId);
    if (!supportsFormatting(doc) || !doc?.editMode || !editor || editor.readOnly || document.querySelector('dialog[open]')) return;
    const start = editor.selectionStart, end = editor.selectionEnd;
    if (action === 'image') {
      const source = editor.value, id = doc.id;
      bridge?.chooseImage(uri => {
        if (!uri || activeId !== id || editor.value !== source) return;
        const content = doc.format === 'Markdown' ? `![Image](<${uri}>)` : `<img src="${uri.replaceAll('&', '&amp;').replaceAll('"', '&quot;')}" alt="Image">`;
        applySourceEdit(editor, ReaderInsertions.block(source, start, end, content));
      });
      return;
    }
    if (action === 'table' || action === 'flowchart') {
      const source = editor.value, id = doc.id;
      ReaderBuilders.open(action, { format: doc.format === 'Word' ? 'HTML' : doc.format,
        onCancel: () => {
          if (activeId === id && editors.get(id) === editor) { editor.focus(); editor.setSelectionRange(start, end); }
        },
        onInsert: content => {
          if (activeId !== id || editors.get(id) !== editor || editor.value !== source) {
            toast('The source changed. Select the insertion point and try again.', true); return;
          }
          applySourceEdit(editor, ReaderInsertions.block(source, start, end, content));
        }
      });
      return;
    }
    if (action === 'link') {
      linkContext = { id: doc.id, editor, start, end, source: editor.value };
      $('link-label').value = editor.value.slice(start, end);
      $('link-url').value = '';
      $('link-error').hidden = true;
      $('link-dialog').showModal();
      $('link-url').focus();
      return;
    }
    applySourceEdit(editor, ReaderFormatting.transform(editor.value, start, end, action, doc.format === 'Word' ? 'HTML' : doc.format));
  }

  function updateProgress() {
    const available = scroller.scrollHeight - scroller.clientHeight;
    const value = activeId ? (available > 1 ? Math.min(100, Math.round(scroller.scrollTop / available * 100)) : 100) : 0;
    $('progress-label').textContent = `${formatNumber(value)}% read`;
    $('progress-bar').style.width = `${value}%`;
  }

  function clearHighlights() {
    results = []; resultIndex = -1;
    CSS.highlights?.delete('reader-search'); CSS.highlights?.delete('reader-current');
    $('search-count').textContent = '';
  }

  function search() {
    clearTimeout(searchTimer);
    clearHighlights();
    const query = $('search-input').value.toLocaleLowerCase();
    if (!query || !activeId) return;
    // Search across inline markup, but keep separate paragraphs separated.
    const walker = document.createTreeWalker(contentRoot(), NodeFilter.SHOW_TEXT);
    const nodes = []; let node, full = '', previousBlock = null;
    while ((node = walker.nextNode())) {
      if (node.parentElement.closest('button,.code-toolbar,style,script')) continue;
      const block = node.parentElement.closest('p,h1,h2,h3,h4,h5,h6,li,td,th,pre');
      if (previousBlock && block !== previousBlock) full += '\n';
      previousBlock = block;
      nodes.push({ node, start: full.length, end: full.length + node.textContent.length });
      full += node.textContent;
    }
    const lowered = full.toLocaleLowerCase();
    let start = 0;
    while ((start = lowered.indexOf(query, start)) >= 0 && results.length < 2000) {
      const end = start + query.length;
      const first = nodes.find(item => item.end > start && item.start <= start);
      const last = nodes.find(item => item.start < end && item.end >= end);
      if (first && last) {
        const range = new Range();
        range.setStart(first.node, start - first.start);
        range.setEnd(last.node, end - last.start);
        results.push(range);
      }
      start = end;
    }
    if (CSS.highlights && results.length) CSS.highlights.set('reader-search', new Highlight(...results));
    resultIndex = results.length ? 0 : -1;
    selectResult(0);
  }

  function selectResult(delta) {
    if (results.length) {
      resultIndex = (resultIndex + delta + results.length) % results.length;
      const selected = results[resultIndex];
      CSS.highlights?.set('reader-current', new Highlight(selected));
      const rect = selected.getBoundingClientRect(), viewport = scroller.getBoundingClientRect();
      scroller.scrollBy({ top: rect.top - viewport.top - viewport.height / 3, behavior: 'instant' });
      $('search-count').textContent = `${formatNumber(resultIndex + 1)} of ${formatNumber(results.length)}${results.length === 2000 ? '+' : ''}`;
    } else $('search-count').textContent = $('search-input').value ? 'No matches' : '';
  }

  function openSearch() {
    $('search-panel').hidden = false;
    $('search-input').focus(); $('search-input').select();
    if ($('search-input').value) search();
  }
  function closeSearch() {
    clearTimeout(searchTimer);
    $('search-panel').hidden = true; clearHighlights(); article.focus({ preventScroll: true });
  }
  function focusMode() {
    const enabled = document.body.classList.toggle('focus-mode');
    $('focus-button').setAttribute('aria-pressed', String(enabled));
    $('focus-button').classList.toggle('active', enabled);
    requestAnimationFrame(updateProgress);
  }
  function command(name) {
    if (document.querySelector('dialog[open]') && name !== 'quit-request') return;
    if (name.startsWith('format-')) formatSelection(name.slice(7));
    if (name === 'open') bridge?.openFiles();
    if (name === 'new') bridge?.newDocument($('new-format').value);
    if (name === 'save') saveDocument();
    if (name === 'save-as') saveDocument(true);
    if (name === 'close' && activeId) closeDocument(activeId);
    if (name === 'edit') setEditMode(!documents.get(activeId)?.editMode);
    if (name === 'beautify') beautifyDocument();
    if (name === 'empty') showDocument(null);
    if (name === 'add-mark') reading.add('mark');
    if (name === 'add-note') reading.add('note');
    if (name === 'resume-annotation') reading.resume();
    if (name === 'search') openSearch();
    if (name === 'focus') focusMode();
    if (name === 'reload' && activeId) bridge?.reloadFile(activeId, sourceOf(documents.get(activeId)));
    if (name === 'quit-request') {
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      const snapshots = {};
      for (const doc of documents.values()) snapshots[doc.id] = sourceOf(doc);
      for (const editor of editors.values()) editor.readOnly = true;
      bridge?.confirmQuit(JSON.stringify(snapshots), () => {
        for (const editor of editors.values()) editor.readOnly = false;
      });
    }
  }

  $('open-file').onclick = $('empty-open').onclick = () => command('open');
  $('new-file').onclick = () => command('new');
  $('save-button').onclick = () => saveDocument();
  $('save-as-button').onclick = () => saveDocument(true);
  $('read-mode').onclick = () => setEditMode(false);
  $('edit-mode').onclick = () => setEditMode(true);
  for (const [id, source] of [['api-preview-swagger', false], ['api-preview-source', true]]) {
    $(id).onclick = () => {
      const doc = documents.get(activeId); if (!doc?.api) return;
      doc.apiSource = source; paintPreview(doc); sync.mount('preview');
    };
  }
  $('beautify-button').onmousedown = event => event.preventDefault();
  $('beautify-button').onclick = beautifyDocument;
  document.querySelectorAll('[data-format]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.onclick = () => formatSelection(button.dataset.format);
  });
  $('link-cancel').onclick = () => $('link-dialog').close();
  $('link-dialog').addEventListener('close', () => {
    if (linkContext && activeId === linkContext.id && editors.has(linkContext.id)) {
      linkContext.editor.focus();
      linkContext.editor.setSelectionRange(linkContext.start, linkContext.end);
    }
    linkContext = null;
  });
  $('link-form').addEventListener('submit', event => {
    event.preventDefault();
    const context = linkContext, doc = documents.get(context?.id);
    if (!doc || context.editor.value !== context.source) {
      $('link-dialog').close(); toast('The source changed. Select the text and insert the link again.', true); return;
    }
    try {
      const operation = ReaderFormatting.link(context.source, context.start, context.end, $('link-label').value, $('link-url').value, doc.format === 'Word' ? 'HTML' : doc.format);
      // Close the modal before restoring editor focus and editing the source.
      linkContext = null; $('link-dialog').close();
      applySourceEdit(context.editor, operation);
    } catch (error) {
      $('link-error').textContent = error.message; $('link-error').hidden = false;
      $('link-url').focus();
    }
  });
  $('editor-direction').onchange = event => {
    const doc = documents.get(activeId);
    if (doc) { doc.editorDirection = event.target.value; showEditor(doc); }
  };
  $('sample-button').onclick = () => bridge?.openSample();
  $('reload-button').onclick = () => command('reload');
  $('search-button').onclick = openSearch;
  $('search-close').onclick = closeSearch;
  $('search-input').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(search, 140); };
  $('search-input').onkeydown = event => {
    if (event.key === 'Enter') { event.preventDefault(); selectResult(event.shiftKey ? -1 : 1); }
  };
  $('search-prev').onclick = () => selectResult(-1);
  $('search-next').onclick = () => selectResult(1);
  $('theme-button').onclick = () => { settings.theme = settings.theme === 'dark' ? 'light' : 'dark'; preferences(); };
  $('focus-button').onclick = focusMode;
  $('fullscreen-button').onclick = () => bridge?.toggleFullscreen();
  $('minimize-button').onclick = () => bridge?.minimize();
  document.querySelectorAll('[data-window-drag]').forEach(region => {
    let press = null;
    const isControl = target => target.closest('button, input, select, textarea, a, [contenteditable], [role="button"]');
    const reset = () => {
      if (press && region.hasPointerCapture(press.id)) region.releasePointerCapture(press.id);
      press = null;
    };
    region.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary || isControl(event.target)) return;
      event.preventDefault();
      press = { id: event.pointerId, x: event.clientX, y: event.clientY };
      region.setPointerCapture(event.pointerId);
    });
    region.addEventListener('pointermove', event => {
      if (!press || event.pointerId !== press.id) return;
      if (!(event.buttons & 1)) { reset(); return; }
      // A click (including the first half of a double-click) must not restore
      // fullscreen. Start a native move only after a deliberate drag.
      if (Math.hypot(event.clientX - press.x, event.clientY - press.y) < 8) return;
      reset();
      bridge?.startWindowMove();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(name => region.addEventListener(name, reset));
    region.addEventListener('dblclick', event => {
      if (event.button !== 0 || isControl(event.target)) return;
      event.preventDefault();
      reset();
      bridge?.toggleFullscreen();
    });
  });
  $('sync-scroll').onchange = () => { settings.syncScroll = $('sync-scroll').checked; preferences(); sync.mount('preview'); };
  $('quit-button').onclick = () => bridge?.quit();
  $('appearance-button').onclick = () => {
    $('appearance-panel').hidden = !$('appearance-panel').hidden;
    $('appearance-button').setAttribute('aria-expanded', String(!$('appearance-panel').hidden));
  };
  $('font-size').oninput = event => { settings.fontSize = Number(event.target.value); preferences(); };
  $('line-height').oninput = event => { settings.lineHeight = Number(event.target.value); preferences(); };
  $('wide-page').onchange = event => { settings.wide = event.target.checked; preferences(); };
  $('reset-appearance').onclick = () => { Object.assign(settings, { fontSize: 17, lineHeight: 2, wide: false }); preferences(); };
  document.querySelectorAll('button[data-direction]').forEach(button => {
    button.onclick = () => {
      settings.direction = button.dataset.direction;
      // A deliberate document-level change supersedes per-block overrides.
      overrides.delete(activeId); preferences();
    };
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.appearance-anchor')) {
      $('appearance-panel').hidden = true;
      $('appearance-button').setAttribute('aria-expanded', 'false');
    }
  });
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.key === 'F11') { event.preventDefault(); bridge?.toggleFullscreen(); return; }
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      const key = event.code || event.key.toLowerCase();
      const name = event.shiftKey
        ? ({ KeyS: 'save-as', s: 'save-as', KeyF: 'focus', f: 'focus', KeyM: 'add-note', m: 'add-note', KeyI: 'beautify', i: 'beautify' })[key]
        : ({ KeyO: 'open', o: 'open', KeyN: 'new', n: 'new', KeyS: 'save', s: 'save', KeyW: 'close', w: 'close', KeyE: 'edit', e: 'edit', KeyF: 'search', f: 'search', KeyR: 'reload', r: 'reload', KeyM: 'add-mark', m: 'add-mark' })[key];
      if (name) { event.preventDefault(); command(name); return; }
    }
    if (document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') {
      if (!$('appearance-panel').hidden) { $('appearance-panel').hidden = true; $('appearance-button').setAttribute('aria-expanded', 'false'); }
      else if (!$('search-panel').hidden) closeSearch();
      else if (document.body.classList.contains('focus-mode')) focusMode();
    }
  });
  scroller.addEventListener('scroll', updateProgress, { passive: true });
  let resizeFrame;
  new ResizeObserver(() => {
    updateProgress();
    cancelAnimationFrame(resizeFrame);
    // Resizing a graph changes article height. Do writes on the next frame
    // instead of feeding layout changes back into the observer delivery.
    resizeFrame = requestAnimationFrame(() => { ReaderDiagrams.resize(article); reading.resize(); sync.resize(); });
  }).observe(article);
  window.addEventListener('resize', updateProgress);
  window.readerApp = { receiveDocument, showDocument, closeDocument, preferences, search, command, setEditMode,
    get settings() { return settings; }, get activeId() { return activeId; } };

  preferences(false);
  if (typeof QWebChannel === 'function' && window.qt?.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, channel => {
      bridge = channel.objects.native;
      bridge.documentLoaded.connect(receiveDocument);
      bridge.documentSaved.connect(receiveSaved);
      bridge.documentClosed.connect(removeDocument);
      bridge.documentActivated.connect(id => showDocument(id));
      bridge.previewReady.connect(receivePreview);
      bridge.previewFailed.connect((id, revision, message) => {
        const doc = documents.get(id);
        if (doc && doc.revision === revision) {
          doc.previewPending = false;
          if (id === activeId) { $('preview-status').textContent = 'Preview unavailable'; toast(message, true); }
        }
      });
      bridge.errorOccurred.connect(message => toast(message, true));
      bridge.busyChanged.connect(busy => { $('loading').hidden = !busy; });
      bridge.settingsLoaded.connect(raw => {
        try { settings = { ...defaults, ...JSON.parse(raw) }; preferences(false); } catch { preferences(false); }
      });
      bridge.libraryChanged.connect(raw => reading.receive(raw));
      bridge.pdfPageReady.connect(raw => pdf.receive(raw));
      bridge.sourceFormatted.connect(receiveSourceFormatted);
      bridge.apiResponse.connect(raw => apiRequests.receive(raw));
      bridge.command.connect(command);
      bridge.ready();
    });
  } else {
    showDocument(null);
    toast('Start the desktop app with python main.py.', true);
  }
})();
