(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const formatNumber = (number) =>
    new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(number);
  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const defaults = {
    theme: 'light',
    direction: 'smart',
    fontSize: 17,
    lineHeight: 2,
    wide: false,
    syncScroll: true,
    previewZoom: 100,
  };
  let settings = { ...defaults },
    bridge,
    activeId = null,
    toastTimer;
  const documents = new Map(),
    positions = new Map(),
    overrides = new Map();
  const editors = new Map(),
    previewTimers = new Map();
  const article = $('document'),
    scroller = $('reading-scroll');
  const reading = ReaderLibrary.create({
    article,
    scroller,
    current: () => documents.get(activeId),
    documents,
    sourceOf,
    native: () => bridge,
    toast,
  });
  const sync = ReaderScrollSync.create({
    article,
    scroller,
    current: () => documents.get(activeId),
    editor: () => editors.get(activeId),
    enabled: () => settings.syncScroll,
  });
  const zoom = ReaderPreviewZoom.create({
    article,
    scroller,
    beforeChange: () => sync.reset(),
    afterChange: () => {
      sync.mount('preview');
      updateProgress();
    },
    changed: (value) => {
      settings.previewZoom = value;
      bridge?.saveSettings(JSON.stringify(settings));
    },
  });
  const pdf = ReaderPDF.create({
    article,
    scroller,
    current: () => documents.get(activeId),
    native: () => bridge,
    toast,
    changed: (source) => {
      const doc = documents.get(activeId);
      doc.source = source;
      updateCaption();
      files.render();
      schedulePreview(doc);
    },
  });
  const contentRoot = () => ReaderOpenAPI.contentRoot(article);
  const apiRequests = ReaderApiRequests.create(() => bridge);
  const api = ReaderOpenAPI.create({
    article,
    current: () => documents.get(activeId),
    requests: apiRequests,
    theme: () => settings.theme,
    direction: () => settings.direction,
    openLink: (href, id) => bridge?.openLink(href, id),
    ready: (doc, first) => {
      reading.mount();
      outline.render(doc);
      if (first) {
        scroller.scrollTo({ top: doc.apiScroll || 0, behavior: 'instant' });
        reading.changed(!positions.has(doc.id));
        sync.mount(doc.editMode ? 'editor' : 'preview');
      }
      if (!$('search-panel').hidden) find.search();
    },
  });

  const workspace = ReaderWorkspace.create({
    documents,
    current: () => activeId,
    activate: showDocument,
    api,
    native: () => bridge,
    settings: () => settings,
    positions,
  });
  $('reading-layout').onchange = () => {
    sourceEditor.setMode(false);
    workspace.setLayout($('reading-layout').value);
  };
  const sidebar = ReaderSidebar.create({
    changed: (state) => {
      settings.sidebar = state;
      bridge?.saveSettings(JSON.stringify(settings));
    },
  });
  settings.sidebar = sidebar.snapshot();

  const find = ReaderSearch.create({
    article,
    scroller,
    contentRoot,
    current: () => activeId,
    formatNumber,
  });
  const outline = ReaderOutline.create({ contentRoot, scroller });
  const files = ReaderFileList.create({
    documents,
    current: () => activeId,
    native: () => bridge,
    sourceOf,
    showDocument,
    closeDocument,
    detachDocument,
    icon,
    formatNumber,
  });
  const sourceEditor = ReaderSourceEditor.create({
    documents,
    current: () => activeId,
    editors,
    workspace,
    sync,
    native: () => bridge,
    toast,
    updateCaption,
    updateProgress,
    renderFiles: () => files.render(),
    schedulePreview,
  });
  ReaderWindowControls.create({ native: () => bridge });

  function toast(message, error = false) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').classList.toggle('error', error);
    $('toast').hidden = false;
    toastTimer = setTimeout(
      () => {
        $('toast').hidden = true;
      },
      error ? 6500 : 2800
    );
  }

  function preferences(save = true) {
    document.body.dataset.theme = settings.theme;
    document.documentElement.style.colorScheme = settings.theme;
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
    $('theme-button').setAttribute(
      'aria-label',
      settings.theme === 'dark' ? 'Light theme' : 'Dark theme'
    );
    document.querySelectorAll('button[data-direction]').forEach((button) => {
      const selected = button.dataset.direction === settings.direction;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    ReaderBidi.apply(article, settings.direction, overrides.get(activeId));
    api.preferences();
    workspace.preferences();
    ReaderDiagrams.refreshTheme(article, settings.theme);
    $('direction-status').textContent = {
      smart: 'Smart direction is on',
      rtl: 'Right-to-left text',
      ltr: 'Left-to-right text',
    }[settings.direction];
    if (save) bridge?.saveSettings(JSON.stringify(settings));
    requestAnimationFrame(updateProgress);
  }

  function viewState(doc) {
    const editor = editors.get(doc.id);
    return {
      scroll: doc.id === activeId ? scroller.scrollTop : positions.get(doc.id) || 0,
      editMode: doc.editMode,
      apiSource: doc.apiSource,
      editorDirection: doc.editorDirection,
      selectionStart: editor?.selectionStart,
      selectionEnd: editor?.selectionEnd,
      editorScroll: editor?.scrollTop,
      preview: !doc.previewPending
        ? { html: doc.html, headings: doc.headings, api: doc.api, words: doc.words }
        : null,
      api: api.snapshot(doc.id),
    };
  }

  function detachDocument(id) {
    const doc = documents.get(id);
    if (!doc || doc.moving) return;
    bridge?.detachDocument(id, sourceOf(doc), '{}');
  }

  function prepareTransfer(doc) {
    // Let pending responses and the latest source preview settle before copying their state.
    setTimeout(() => {
      if (!doc.moving || !documents.has(doc.id)) return;
      if (apiRequests.count(doc.id) || doc.previewPending) {
        prepareTransfer(doc);
        return;
      }
      bridge?.prepareTransfer(doc.id, sourceOf(doc), JSON.stringify(viewState(doc)));
    }, 50);
  }

  function closeDocument(id) {
    const doc = documents.get(id);
    if (!doc || doc.closing || doc.moving) return;
    if (bridge) {
      doc.closing = true;
      bridge.closeFile(id, sourceOf(doc), () => {
        doc.closing = false;
      });
    } else removeDocument(id);
  }

  function removeDocument(id) {
    const keys = [...documents.keys()];
    const index = keys.indexOf(id);
    api.dispose(id);
    documents.delete(id);
    positions.delete(id);
    overrides.delete(id);
    clearTimeout(previewTimers.get(id));
    previewTimers.delete(id);
    editors.get(id)?.remove();
    editors.delete(id);
    if (activeId === id) {
      activeId = null;
      const remaining = [...documents.keys()];
      showDocument(remaining[Math.min(index, remaining.length - 1)] || null);
    } else {
      files.render();
      reading.refresh();
      workspace.render();
    }
  }

  function enhanceDocument() {
    ReaderBidi.prepare(article);
    // Keep direction controls out of nested list items and table cells: their
    // parent paragraph/table can be adjusted using the global direction control.
    article.querySelectorAll('h1,h2,h3,h4,h5,h6,p').forEach((block) => {
      if (block.closest('li,th,td')) return;
      const button = document.createElement('button');
      button.className = 'block-direction';
      button.innerHTML = icon('direction');
      button.title = 'Change this block: automatic → right to left → left to right';
      button.setAttribute('aria-label', 'Change this block’s direction');
      button.onclick = () => {
        const values = overrides.get(activeId) || {};
        const key = block.dataset.block;
        const next = values[key] === 'rtl' ? 'ltr' : values[key] === 'ltr' ? null : 'rtl';
        if (next) values[key] = next;
        else delete values[key];
        overrides.set(activeId, values);
        ReaderBidi.apply(article, settings.direction, values);
        toast(
          next === 'rtl'
            ? 'This block: right to left'
            : next === 'ltr'
              ? 'This block: left to right'
              : 'This block follows the document direction'
        );
      };
      block.append(button);
    });
    article.querySelectorAll('pre').forEach((pre) => {
      const code = pre.querySelector('code');
      if (!code) return;
      const bar = document.createElement('div');
      bar.className = 'code-toolbar';
      const label = document.createElement('span');
      label.className = 'code-language';
      label.textContent =
        [...code.classList].find((name) => name.startsWith('language-'))?.slice(9) || 'plain text';
      const copy = document.createElement('button');
      copy.className = 'copy-code';
      copy.innerHTML = icon('copy') + 'Copy code';
      copy.onclick = () => {
        bridge?.copyText(code.textContent);
        toast('Code copied');
      };
      bar.append(label, copy);
      pre.prepend(bar);
    });
    article.querySelectorAll('table').forEach((table) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-scroll';
      table.before(wrapper);
      wrapper.append(table);
    });
    article.querySelectorAll('a').forEach((link) => {
      link.onclick = (event) => {
        event.preventDefault();
        const href = link.getAttribute('href') || '';
        if (href.startsWith('#')) {
          try {
            document
              .getElementById(decodeURIComponent(href.slice(1)))
              ?.scrollIntoView({ behavior: 'smooth' });
          } catch {
            /* Invalid fragment. */
          }
        } else bridge?.openLink(href, activeId);
      };
    });
    ReaderDiagrams.mount(article, {
      theme: settings.theme,
      copy: (source) => {
        bridge?.copyText(source);
        toast('Diagram source copied');
      },
    });
  }

  function paintPreview(doc) {
    sync.reset();
    const top = scroller.scrollTop;
    find.clear();
    article.innerHTML = doc?.html || '';
    article.classList.toggle('pdf-document', doc?.format === 'PDF');
    const apiView = Boolean(doc?.api && !doc.apiSource);
    if (doc) {
      doc.apiRendering = apiView;
      doc.apiScroll = top;
    }
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
    $('reading-time').textContent = doc?.words
      ? `${formatNumber(Math.max(1, Math.ceil(doc.words / 200)))} min read`
      : 'Empty document';
    if (doc) {
      if (!doc.html.trim()) article.innerHTML = '<p class="empty-document">This file is empty.</p>';
      if (apiView) api.show(doc);
      else enhanceDocument();
    }
    reading.mount();
    pdf.mount();
    outline.render(doc);
    preferences(false);
    scroller.scrollTo({ top, behavior: 'instant' });
    if (!$('search-panel').hidden) find.search();
    requestAnimationFrame(updateProgress);
  }

  function showDocument(id, refresh = false) {
    if (activeId && documents.has(activeId)) positions.set(activeId, scroller.scrollTop);
    activeId = id;
    const doc = documents.get(id);
    article.inert = Boolean(doc?.moving);
    paintPreview(doc);
    workspace.render();
    sourceEditor.show(doc);
    updateCaption();
    files.render();
    const target = refresh
      ? Math.min(positions.get(id) || 0, scroller.scrollHeight)
      : positions.get(id) || 0;
    if (doc?.apiRendering) doc.apiScroll = target;
    scroller.scrollTo({ top: target, behavior: 'instant' });
    reading.changed(!positions.has(id));
    sync.mount('preview');
    if (id) bridge?.activateDocument(id);
    if (!$('search-panel').hidden) find.search();
    requestAnimationFrame(updateProgress);
  }

  function receiveDocument(payload) {
    const doc = JSON.parse(payload);
    const previous = documents.get(doc.id);
    const refreshing = Boolean(previous);
    if (refreshing) {
      overrides.delete(doc.id);
      api.dispose(doc.id);
    }
    clearTimeout(previewTimers.get(doc.id));
    previewTimers.delete(doc.id);
    editors.get(doc.id)?.remove();
    editors.delete(doc.id);
    doc.editMode = previous?.editMode ?? !doc.path;
    doc.apiSource = previous?.apiSource || false;
    doc.editorDirection = previous?.editorDirection || (doc.format === 'Markdown' ? 'auto' : 'ltr');
    doc.revision = (previous?.revision || 0) + 1;
    doc.savedSource = doc.savedSource ?? doc.source;
    doc.dirty = doc.source !== doc.savedSource;
    const transferred = doc.viewState;
    delete doc.viewState;
    if (transferred) {
      doc.editMode = Boolean(transferred.editMode);
      doc.apiSource = Boolean(transferred.apiSource);
      doc.editorDirection = transferred.editorDirection || doc.editorDirection;
      doc.apiInitial = transferred.api;
      positions.set(doc.id, transferred.scroll || 0);
      if (transferred.preview) Object.assign(doc, transferred.preview);
    }
    if (workspace.mode !== 'single') doc.editMode = false;
    documents.set(doc.id, doc);
    showDocument(doc.id, refreshing);
    if (transferred) {
      const editor = editors.get(doc.id);
      if (editor) {
        editor.setSelectionRange(transferred.selectionStart || 0, transferred.selectionEnd || 0);
        editor.scrollTop = transferred.editorScroll || 0;
      }
      if (!transferred.preview) schedulePreview(doc, 0);
      bridge?.acceptTransfer(doc.id);
      toast('Tab moved to this window');
    }
    if (!doc.path) editors.get(doc.id)?.focus();
  }

  function sourceOf(doc) {
    return editors.get(doc.id)?.value ?? doc.source;
  }

  function updateCaption() {
    const doc = documents.get(activeId);
    if (doc) doc.dirty = sourceOf(doc) !== doc.savedSource;
    $('current-filename').textContent = doc?.name || 'Khana';
    $('current-filename').title = doc?.path || 'Not saved to disk';
    $('sample-badge').hidden = !doc?.sample;
    $('reload-button').disabled = !doc?.path || Boolean(doc?.moving);
    $('save-button').disabled = $('save-as-button').disabled =
      !doc || Boolean(doc?.saving || doc?.moving);
    $('read-mode').disabled = !doc;
    $('edit-mode').disabled =
      !doc || (doc.format === 'PDF' && !article.querySelector('[data-editable=true]'));
    $('save-status').textContent = !doc
      ? 'No document'
      : doc.moving
        ? 'Moving tab…'
        : doc.saving
          ? 'Saving…'
          : doc.dirty
            ? 'Unsaved changes'
            : !doc.path
              ? 'Not saved yet'
              : 'Saved';
    $('save-status').classList.toggle('dirty', Boolean(doc?.dirty));
    $('editor-name').textContent =
      doc?.format === 'Word' ? 'Word source (HTML)' : `${doc?.format || 'Document'} source`;
    $('document-format').textContent = doc?.format || '—';
    $('encoding').textContent = doc?.encoding || '—';
    $('beautify-button').disabled = Boolean(doc?.formatting);
    $('beautify-button').textContent = doc?.formatting ? 'Formatting…' : 'Format document';
    bridge?.setDocumentTitle(doc ? `${doc.dirty ? '● ' : ''}${doc.name}` : '');
    reading.refresh();
  }

  function schedulePreview(doc, delay = 300) {
    clearTimeout(previewTimers.get(doc.id));
    doc.revision++;
    doc.previewPending = true;
    if (activeId === doc.id) $('preview-status').textContent = 'Updating preview…';
    previewTimers.set(
      doc.id,
      setTimeout(() => {
        previewTimers.delete(doc.id);
        if (documents.has(doc.id)) bridge?.previewDocument(doc.id, sourceOf(doc), doc.revision);
      }, delay)
    );
  }

  function receivePreview(payload) {
    const preview = JSON.parse(payload),
      doc = documents.get(preview.id);
    if (!doc || preview.revision !== doc.revision) return;
    Object.assign(doc, {
      html: preview.html,
      headings: preview.headings,
      words: preview.words,
      api: preview.api || null,
      previewPending: false,
    });
    overrides.delete(doc.id);
    api.update(doc);
    workspace.render();
    if (activeId === doc.id) {
      paintPreview(doc);
      sync.preview();
      $('preview-status').textContent = 'Live preview';
    }
  }

  function receiveSaved(payload) {
    const saved = JSON.parse(payload),
      doc = documents.get(saved.id);
    if (!doc) return;
    for (const key of [
      'path',
      'name',
      'size',
      'fingerprint',
      'sample',
      'format',
      'encoding',
      'codec',
      'bom',
      'newline',
      'savedSource',
    ])
      doc[key] = saved[key];
    doc.source = sourceOf(doc);
    doc.dirty = doc.source !== doc.savedSource;
    updateCaption();
    files.render();
    schedulePreview(doc, 0);
    toast(`Saved ${doc.name}`);
  }

  function saveDocument(saveAs = false) {
    const doc = documents.get(activeId);
    if (!doc || doc.saving || doc.moving) return;
    doc.saving = true;
    updateCaption();
    bridge?.saveDocument(doc.id, sourceOf(doc), saveAs, () => {
      doc.saving = false;
      updateCaption();
    });
  }

  function updateProgress() {
    const available = scroller.scrollHeight - scroller.clientHeight;
    const value = activeId
      ? available > 1
        ? Math.min(100, Math.round((scroller.scrollTop / available) * 100))
        : 100
      : 0;
    $('progress-label').textContent = `${formatNumber(value)}% read`;
    $('progress-bar').style.width = `${value}%`;
  }

  function focusMode() {
    const enabled = document.body.classList.toggle('focus-mode');
    $('focus-button').setAttribute('aria-pressed', String(enabled));
    $('focus-button').classList.toggle('active', enabled);
    requestAnimationFrame(updateProgress);
  }

  function requestQuit() {
    document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
    const snapshots = {};
    for (const doc of documents.values()) snapshots[doc.id] = sourceOf(doc);
    for (const editor of editors.values()) editor.readOnly = true;
    bridge?.confirmQuit(JSON.stringify(snapshots), () => {
      for (const [id, editor] of editors) editor.readOnly = Boolean(documents.get(id)?.moving);
    });
  }

  const commands = new Map(
    Object.entries({
      open: () => bridge?.openFiles(),
      new: () => bridge?.newDocument($('new-format').value),
      save: () => saveDocument(),
      'save-as': () => saveDocument(true),
      close: () => {
        if (activeId) closeDocument(activeId);
      },
      edit: () => sourceEditor.setMode(!documents.get(activeId)?.editMode),
      beautify: () => sourceEditor.beautify(),
      empty: () => showDocument(null),
      'add-mark': () => reading.add('mark'),
      'add-note': () => reading.add('note'),
      'resume-annotation': () => reading.resume(),
      search: () => find.open(),
      focus: focusMode,
      reload: () => {
        const doc = documents.get(activeId);
        if (doc && !doc.moving) bridge?.reloadFile(doc.id, sourceOf(doc));
      },
      'quit-request': requestQuit,
      'tab-drag-finished': () => document.body.classList.remove('tab-dragging'),
      'tab-transfer-wait': () => toast('Moving tab… Waiting for its current requests and preview.'),
    })
  );

  function command(name) {
    if (document.querySelector('dialog[open]') && name !== 'quit-request') return;
    if (name.startsWith('transfer-started:') || name.startsWith('transfer-failed:')) {
      const id = name.slice(name.indexOf(':') + 1),
        doc = documents.get(id);
      if (doc) {
        doc.moving = name.startsWith('transfer-started:');
        const editor = editors.get(id);
        if (editor) editor.readOnly = doc.moving;
        if (id === activeId) article.inert = doc.moving;
        api.setMoving(id, doc.moving);
        files.render();
        updateCaption();
        if (doc.moving) prepareTransfer(doc);
      }
      return;
    }
    if (name.startsWith('format-')) {
      sourceEditor.format(name.slice(7));
      return;
    }
    commands.get(name)?.();
  }

  $('open-file').onclick = $('empty-open').onclick = () => command('open');
  $('new-file').onclick = () => command('new');
  $('save-button').onclick = () => saveDocument();
  $('save-as-button').onclick = () => saveDocument(true);
  $('read-mode').onclick = () => sourceEditor.setMode(false);
  $('edit-mode').onclick = () => sourceEditor.setMode(true);
  for (const [id, source] of [
    ['api-preview-swagger', false],
    ['api-preview-source', true],
  ]) {
    $(id).onclick = () => {
      const doc = documents.get(activeId);
      if (!doc?.api) return;
      doc.apiSource = source;
      paintPreview(doc);
      sync.mount('preview');
    };
  }
  $('sample-button').onclick = () => bridge?.openSample();
  $('reload-button').onclick = () => command('reload');
  $('theme-button').onclick = () => {
    settings.theme = settings.theme === 'dark' ? 'light' : 'dark';
    preferences();
  };
  $('focus-button').onclick = focusMode;
  $('sync-scroll').onchange = () => {
    settings.syncScroll = $('sync-scroll').checked;
    preferences();
    sync.mount('preview');
  };
  $('quit-button').onclick = () => bridge?.quit();
  $('appearance-button').onclick = () => {
    $('appearance-panel').hidden = !$('appearance-panel').hidden;
    $('appearance-button').setAttribute('aria-expanded', String(!$('appearance-panel').hidden));
  };
  $('font-size').oninput = (event) => {
    settings.fontSize = Number(event.target.value);
    preferences();
  };
  $('line-height').oninput = (event) => {
    settings.lineHeight = Number(event.target.value);
    preferences();
  };
  $('wide-page').onchange = (event) => {
    settings.wide = event.target.checked;
    preferences();
  };
  $('reset-appearance').onclick = () => {
    Object.assign(settings, { fontSize: 17, lineHeight: 2, wide: false });
    preferences();
  };
  document.querySelectorAll('button[data-direction]').forEach((button) => {
    button.onclick = () => {
      settings.direction = button.dataset.direction;
      // A deliberate document-level change supersedes per-block overrides.
      overrides.delete(activeId);
      preferences();
    };
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.appearance-anchor')) {
      $('appearance-panel').hidden = true;
      $('appearance-button').setAttribute('aria-expanded', 'false');
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.key === 'F11') {
      event.preventDefault();
      bridge?.toggleFullscreen();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      const key = event.code || event.key.toLowerCase();
      const name = event.shiftKey
        ? {
            KeyS: 'save-as',
            s: 'save-as',
            KeyF: 'focus',
            f: 'focus',
            KeyM: 'add-note',
            m: 'add-note',
            KeyI: 'beautify',
            i: 'beautify',
          }[key]
        : {
            KeyO: 'open',
            o: 'open',
            KeyN: 'new',
            n: 'new',
            KeyS: 'save',
            s: 'save',
            KeyW: 'close',
            w: 'close',
            KeyE: 'edit',
            e: 'edit',
            KeyF: 'search',
            f: 'search',
            KeyR: 'reload',
            r: 'reload',
            KeyM: 'add-mark',
            m: 'add-mark',
          }[key];
      if (name) {
        event.preventDefault();
        command(name);
        return;
      }
    }
    if (document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') {
      if (!$('appearance-panel').hidden) {
        $('appearance-panel').hidden = true;
        $('appearance-button').setAttribute('aria-expanded', 'false');
      } else if (!$('search-panel').hidden) find.close();
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
    resizeFrame = requestAnimationFrame(() => {
      ReaderDiagrams.resize(article);
      reading.resize();
      sync.resize();
    });
  }).observe(article);
  window.addEventListener('resize', updateProgress);
  window.readerApp = {
    receiveDocument,
    showDocument,
    closeDocument,
    preferences,
    search: find.search,
    command,
    setEditMode: sourceEditor.setMode,
    detachDocument,
    get settings() {
      return settings;
    },
    get activeId() {
      return activeId;
    },
  };

  preferences(false);
  if (typeof QWebChannel === 'function' && window.qt?.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, (channel) => {
      bridge = channel.objects.native;
      $('app-version').textContent = `/ ${bridge.appVersion}`;
      bridge.documentLoaded.connect(receiveDocument);
      bridge.documentSaved.connect(receiveSaved);
      bridge.documentClosed.connect(removeDocument);
      bridge.documentActivated.connect((id) => showDocument(id));
      bridge.previewReady.connect(receivePreview);
      bridge.previewFailed.connect((id, revision, message) => {
        const doc = documents.get(id);
        if (doc && doc.revision === revision) {
          doc.previewPending = false;
          if (id === activeId) {
            $('preview-status').textContent = 'Preview unavailable';
            toast(message, true);
          }
        }
      });
      bridge.errorOccurred.connect((message) => toast(message, true));
      bridge.busyChanged.connect((busy) => {
        $('loading').hidden = !busy;
      });
      bridge.settingsLoaded.connect((raw) => {
        try {
          settings = { ...defaults, ...JSON.parse(raw) };
          sidebar.restore(settings.sidebar);
          settings.sidebar = sidebar.snapshot();
          preferences(false);
        } catch {
          preferences(false);
        }
      });
      bridge.libraryChanged.connect((raw) => reading.receive(raw));
      bridge.pdfPageReady.connect((raw) => {
        const result = JSON.parse(raw);
        pdf.receive(result);
        workspace.receivePdf(result);
      });
      bridge.sourceFormatted.connect(sourceEditor.receiveFormatted);
      bridge.apiResponse.connect((raw) => apiRequests.receive(raw));
      bridge.command.connect(command);
      bridge.ready();
    });
  } else {
    showDocument(null);
    toast('Start the desktop app with python main.py.', true);
  }
})();
