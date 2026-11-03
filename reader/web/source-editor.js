/* Source editing, formatting dialogs and undo-preserving text operations. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({
    documents,
    current,
    editors,
    workspace,
    sync,
    lineNumbers,
    native,
    toast,
    updateCaption,
    updateProgress,
    renderFiles,
    schedulePreview,
  }) {
    let linkContext = null,
      lineContext = null;
    const supportsFormatting = (doc) => ['Markdown', 'HTML', 'Word'].includes(doc?.format);
    const supportsBeautify = (doc) => ['JSON', 'YAML', 'XML'].includes(doc?.format);
    function ensureEditor(doc) {
      if (editors.has(doc.id)) return editors.get(doc.id);
      const editor = document.createElement('textarea');
      editor.className = 'source-editor';
      editor.value = doc.source;
      editor.spellcheck = false;
      editor.setAttribute('autocapitalize', 'off');
      editor.setAttribute('autocomplete', 'off');
      editor.setAttribute('aria-label', `${doc.format} source editor`);
      editor.placeholder = ['HTML', 'Word'].includes(doc.format)
        ? '<h1>Your next idea</h1>\n<p>Start writing…</p>'
        : doc.format === 'Markdown'
          ? '# Your next idea\n\nStart writing in any language…'
          : `Start writing ${doc.format}…`;
      editor.addEventListener('input', () => {
        doc.source = editor.value;
        const wasDirty = doc.dirty;
        doc.dirty = doc.source !== doc.savedSource;
        updateCaption();
        updateCursor();
        if (wasDirty !== doc.dirty) renderFiles();
        schedulePreview(doc);
      });
      editor.addEventListener('compositionend', () => schedulePreview(doc));
      editor.addEventListener('keydown', (event) => {
        if (
          !supportsFormatting(doc) ||
          !(event.ctrlKey || event.metaKey) ||
          event.altKey ||
          event.isComposing
        )
          return;
        const key = event.code || event.key.toLowerCase();
        const action = event.shiftKey
          ? { KeyX: 'strike', x: 'strike' }[key]
          : {
              KeyB: 'bold',
              b: 'bold',
              KeyI: 'italic',
              i: 'italic',
              KeyK: 'link',
              k: 'link',
              Backquote: 'code',
              '`': 'code',
            }[key];
        if (action) {
          event.preventDefault();
          event.stopPropagation();
          formatSelection(action);
        }
      });
      editor.addEventListener('keyup', updateCursor);
      editor.addEventListener('click', updateCursor);
      editor.addEventListener('select', updateCursor);
      editors.set(doc.id, editor);
      $('editor-container').append(editor);
      sync.bind(editor);
      lineNumbers.bind(editor);
      return editor;
    }

    function showEditor(doc) {
      const enabled = Boolean(doc?.editMode) && workspace.mode === 'single';
      document.body.classList.toggle('editing', enabled);
      $('mode-label').textContent = enabled ? 'Writing mode' : 'Reading mode';
      $('direction-label').textContent = enabled ? 'Preview direction' : 'Text direction';
      $('editor-pane').hidden = !enabled || doc?.format === 'PDF';
      $('format-toolbar').hidden = !supportsFormatting(doc);
      $('beautify-button').hidden = !enabled || !supportsBeautify(doc);
      $('go-to-line-button').disabled = !doc || doc.format === 'PDF' || Boolean(doc.moving);
      $('word-editing-note').hidden = doc?.format !== 'Word';
      $('sync-control').hidden = !enabled || doc?.format === 'PDF';
      $('read-mode').classList.toggle('active', !enabled);
      $('edit-mode').classList.toggle('active', enabled);
      $('read-mode').setAttribute('aria-pressed', String(!enabled));
      $('edit-mode').setAttribute('aria-pressed', String(enabled));
      for (const [id, editor] of editors) editor.hidden = id !== doc?.id;
      if (enabled && doc?.format !== 'PDF') {
        const editor = ensureEditor(doc);
        editor.hidden = false;
        editor.readOnly = Boolean(doc.moving);
        editor.dir = doc.editorDirection;
        editor.dataset.direction = doc.editorDirection;
        $('editor-direction').value = doc.editorDirection;
      }
      $('preview-status').textContent = doc?.previewPending ? 'Updating preview…' : 'Live preview';
      updateCursor();
      document.body.classList.toggle('editing-pdf', enabled && doc?.format === 'PDF');
    }

    function setEditMode(enabled) {
      const doc = documents.get(current());
      if (!doc) return;
      if (enabled) workspace.setLayout('single');
      doc.editMode = enabled;
      showEditor(doc);
      if (enabled) editors.get(doc.id)?.focus({ preventScroll: true });
      sync.mount('preview');
      requestAnimationFrame(updateProgress);
    }

    function updateCursor() {
      lineNumbers.refresh();
      const editor = editors.get(current());
      if (!editor) return;
      const before = editor.value.slice(0, editor.selectionStart).split('\n');
      $('cursor-position').textContent =
        `Ln ${before.length}, Col ${[...before.at(-1)].length + 1}`;
    }

    const sourceOf = (doc) => (editors.get(doc.id)?.value ?? doc.source).replace(/\r\n?/g, '\n');
    function goToLine() {
      const doc = documents.get(current());
      if (!doc || doc.moving || document.querySelector('dialog[open]')) return;
      if (doc.format === 'PDF') {
        toast('Go to line is available for documents with editable source text.');
        return;
      }
      const editor = editors.get(doc.id),
        count = sourceOf(doc).split('\n').length,
        line = editor ? editor.value.slice(0, editor.selectionStart).split('\n').length : 1;
      lineContext = { id: doc.id, focus: document.activeElement };
      $('go-to-line-hint').textContent = `Enter a line number from 1 to ${count}.`;
      $('go-to-line-input').value = line;
      $('go-to-line-input').removeAttribute('aria-invalid');
      $('go-to-line-error').hidden = true;
      $('go-to-line-dialog').showModal();
      $('go-to-line-input').focus();
      $('go-to-line-input').select();
    }
    $('cursor-position').onclick = goToLine;
    $('go-to-line-button').onclick = goToLine;
    $('go-to-line-cancel').onclick = () => $('go-to-line-dialog').close();
    $('go-to-line-dialog').addEventListener('close', () => {
      if ($('go-to-line-dialog').open) return;
      if (lineContext?.focus?.isConnected) lineContext.focus.focus({ preventScroll: true });
      lineContext = null;
    });
    $('go-to-line-input').addEventListener('input', () => {
      $('go-to-line-input').removeAttribute('aria-invalid');
      $('go-to-line-error').hidden = true;
    });
    $('go-to-line-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const doc = documents.get(current());
      if (!doc || doc.id !== lineContext?.id || doc.moving) {
        $('go-to-line-dialog').close();
        return;
      }
      const input = $('go-to-line-input'),
        value = input.value
          .trim()
          .replace(/[۰-۹٠-٩]/g, (digit) => String(digit.charCodeAt(0) & 15)),
        line = Number(value),
        source = sourceOf(doc),
        count = source.split('\n').length;
      if (!/^\d+$/.test(value) || !Number.isSafeInteger(line) || line < 1 || line > count) {
        $('go-to-line-error').textContent = `Enter a whole line number from 1 to ${count}.`;
        $('go-to-line-error').hidden = false;
        input.setAttribute('aria-invalid', 'true');
        input.focus();
        return;
      }
      lineContext = null;
      $('go-to-line-dialog').close();
      if (!doc.editMode) {
        sync.revealPreviewLine(line - 1);
        return;
      }
      const editor = editors.get(doc.id);
      let offset = 0;
      for (let i = 1; i < line; i++) offset = editor.value.indexOf('\n', offset) + 1;
      editor.setSelectionRange(offset, offset);
      editor.focus({ preventScroll: true });
      updateCursor();
      sync.revealLine(line - 1);
    });

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
      const doc = documents.get(current());
      if (doc && doc.source !== editor.value)
        editor.dispatchEvent(new Event('input', { bubbles: true }));
      updateCursor();
      return true;
    }

    function beautifyDocument() {
      const doc = documents.get(current()),
        editor = editors.get(current());
      if (
        !native() ||
        !doc?.editMode ||
        !supportsBeautify(doc) ||
        !editor ||
        editor.readOnly ||
        doc.formatting
      )
        return;
      doc.formatting = {
        editor,
        source: editor.value,
        start: editor.selectionStart,
        end: editor.selectionEnd,
        top: editor.scrollTop,
      };
      updateCaption();
      native().formatSource(doc.id, editor.value);
    }

    function receiveSourceFormatted(raw) {
      const result = JSON.parse(raw),
        doc = documents.get(result.id),
        context = doc?.formatting;
      if (!context) return;
      doc.formatting = null;
      updateCaption();
      if (current() !== result.id || !doc.editMode) return;
      if (context.editor !== editors.get(result.id) || context.editor.value !== context.source) {
        toast('The source changed while formatting. Try Format document again.', true);
        return;
      }
      if (result.error) {
        toast(result.error, true);
        return;
      }
      if (result.source === context.source) {
        toast('The document is already formatted.');
        return;
      }
      if (
        applySourceEdit(context.editor, {
          start: 0,
          end: context.source.length,
          text: result.source,
          selectionStart: Math.min(context.start, result.source.length),
          selectionEnd: Math.min(context.end, result.source.length),
        })
      ) {
        context.editor.scrollTop = context.top;
        toast('Document formatted. Ctrl+Z to undo; Save to write changes.');
      }
    }

    function formatSelection(action) {
      const doc = documents.get(current()),
        editor = editors.get(current());
      if (
        !supportsFormatting(doc) ||
        !doc?.editMode ||
        !editor ||
        editor.readOnly ||
        document.querySelector('dialog[open]')
      )
        return;
      const start = editor.selectionStart,
        end = editor.selectionEnd;
      if (action === 'image') {
        const source = editor.value,
          id = doc.id;
        native()?.chooseImage((uri) => {
          if (!uri || current() !== id || editor.value !== source) return;
          const content =
            doc.format === 'Markdown'
              ? `![Image](<${uri}>)`
              : `<img src="${uri.replaceAll('&', '&amp;').replaceAll('"', '&quot;')}" alt="Image">`;
          applySourceEdit(editor, ReaderInsertions.block(source, start, end, content));
        });
        return;
      }
      if (action === 'table' || action === 'flowchart') {
        const source = editor.value,
          id = doc.id;
        ReaderBuilders.open(action, {
          format: doc.format === 'Word' ? 'HTML' : doc.format,
          onCancel: () => {
            if (current() === id && editors.get(id) === editor) {
              editor.focus();
              editor.setSelectionRange(start, end);
            }
          },
          onInsert: (content) => {
            if (current() !== id || editors.get(id) !== editor || editor.value !== source) {
              toast('The source changed. Select the insertion point and try again.', true);
              return;
            }
            applySourceEdit(editor, ReaderInsertions.block(source, start, end, content));
          },
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
      applySourceEdit(
        editor,
        ReaderFormatting.transform(
          editor.value,
          start,
          end,
          action,
          doc.format === 'Word' ? 'HTML' : doc.format
        )
      );
    }

    $('beautify-button').onmousedown = (event) => event.preventDefault();
    $('beautify-button').onclick = beautifyDocument;
    document.querySelectorAll('[data-format]').forEach((button) => {
      button.addEventListener('mousedown', (event) => event.preventDefault());
      button.onclick = () => formatSelection(button.dataset.format);
    });
    $('link-cancel').onclick = () => $('link-dialog').close();
    $('link-dialog').addEventListener('close', () => {
      if (linkContext && current() === linkContext.id && editors.has(linkContext.id)) {
        linkContext.editor.focus();
        linkContext.editor.setSelectionRange(linkContext.start, linkContext.end);
      }
      linkContext = null;
    });
    $('link-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const context = linkContext,
        doc = documents.get(context?.id);
      if (!doc || context.editor.value !== context.source) {
        $('link-dialog').close();
        toast('The source changed. Select the text and insert the link again.', true);
        return;
      }
      try {
        const operation = ReaderFormatting.link(
          context.source,
          context.start,
          context.end,
          $('link-label').value,
          $('link-url').value,
          doc.format === 'Word' ? 'HTML' : doc.format
        );
        // Close the modal before restoring editor focus and editing the source.
        linkContext = null;
        $('link-dialog').close();
        applySourceEdit(context.editor, operation);
      } catch (error) {
        $('link-error').textContent = error.message;
        $('link-error').hidden = false;
        $('link-url').focus();
      }
    });
    $('editor-direction').onchange = (event) => {
      const doc = documents.get(current());
      if (doc) {
        doc.editorDirection = event.target.value;
        showEditor(doc);
      }
    };

    return {
      show: showEditor,
      setMode: setEditMode,
      format: formatSelection,
      beautify: beautifyDocument,
      goToLine,
      receiveFormatted: receiveSourceFormatted,
    };
  }
  window.ReaderSourceEditor = { create };
})();
