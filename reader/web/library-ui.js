(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function create({
    article,
    scroller,
    current,
    documents,
    sourceOf,
    native,
    toast,
    bindFileMenu,
    categories,
  }) {
    let entries = new Map(),
      available = false,
      starredOnly = false,
      blocks = [],
      dialogContext = null,
      intent = null;
    const record = () => entries.get(current()?.path);
    const items = () => record()?.annotations || [];
    const persistent = () => available && current()?.path && !current()?.sample;
    const canAdd = () =>
      persistent() && !current().dirty && !current().previewPending && blocks.length;
    const visibleEntries = () =>
      [...entries.values()].filter((entry) => !starredOnly || entry.starred);
    function orderedDocuments() {
      const rank = new Map([...entries.keys()].map((path, index) => [path, index]));
      return [...documents.values()].sort(
        (a, b) => (rank.get(a.path) ?? Infinity) - (rank.get(b.path) ?? Infinity)
      );
    }

    function libraryList() {
      const container = $('library-list');
      $('library-all').classList.toggle('active', !starredOnly);
      $('library-all').setAttribute('aria-pressed', String(!starredOnly));
      $('library-starred').classList.toggle('active', starredOnly);
      $('library-starred').setAttribute('aria-pressed', String(starredOnly));
      const records = visibleEntries();
      const open = new Set([...documents.values()].map((doc) => doc.path));
      categories.render(
        container,
        records,
        (entry) => entry.categoryId,
        (entry) => {
          const row = element(
            'div',
            `library-item${current()?.path === entry.path ? ' active' : ''}`
          );
          row.dataset.path = entry.path;
          const star = element('button', 'library-star', entry.starred ? '★' : '☆');
          star.type = 'button';
          star.title = entry.starred ? 'Unstar document' : 'Star document';
          star.setAttribute('aria-label', `${star.title}: ${entry.name}`);
          star.setAttribute('aria-pressed', String(entry.starred));
          star.onclick = () => native()?.starDocument(entry.path, !entry.starred);
          const select = element('button', 'library-open');
          select.type = 'button';
          select.title = entry.path;
          select.innerHTML = ReaderFileIcons.markup(entry);
          const text = element('span', 'library-text');
          const name = element('span', 'library-name', entry.name);
          name.dir = 'auto';
          const count = entry.annotations.length;
          text.append(
            name,
            element(
              'span',
              'library-info',
              entry.missing
                ? 'File not found'
                : `${entry.pinned ? 'Pinned · ' : ''}${entry.format}${count ? ` · ${count} mark${count === 1 ? '' : 's'} / note${count === 1 ? '' : 's'}` : ''}`
            )
          );
          select.append(text);
          select.onclick = () => native()?.openLibrary(entry.path);
          const forget = element('button', 'library-forget', '×');
          forget.type = 'button';
          forget.disabled = open.has(entry.path);
          forget.title = forget.disabled
            ? 'Close the document before removing it from the library'
            : 'Remove from library (keeps the source file)';
          forget.setAttribute('aria-label', `Remove ${entry.name} from library`);
          forget.onclick = () => native()?.forgetDocument(entry.path);
          row.append(star, select, forget);
          bindFileMenu(row, { path: entry.path }, select);
          return row;
        },
        'library'
      );
      if (!container.children.length)
        container.append(
          element(
            'div',
            'library-empty',
            !available
              ? 'Library unavailable.'
              : starredOnly
                ? 'Star a document to keep it here.'
                : 'Opened files stay here after you close the app.'
          )
        );
    }

    function annotationList() {
      const container = $('annotation-list');
      container.replaceChildren();
      if (!items().length)
        container.append(
          element(
            'p',
            'library-empty',
            'Add marks to remember places, or notes to keep your thoughts.'
          )
        );
      for (const item of items()) {
        const row = element(
          'div',
          `annotation-item${record()?.resumeId === item.id ? ' current' : ''}`
        );
        row.dataset.id = item.id;
        const jump = element('button', 'annotation-jump', item.label);
        jump.type = 'button';
        jump.dir = 'auto';
        jump.onclick = () => go(item.id);
        const location = ReaderAnnotations.locate(blocks, item.anchor);
        const meta = element(
          'div',
          'annotation-meta',
          `${item.kind === 'note' ? 'Note' : 'Mark'} · ${Math.round(item.anchor.progress * 100)}%${record()?.resumeId === item.id ? ' · Continue here' : ''}${location.exact ? '' : ' · Text changed'}`
        );
        const quote = element(
          'div',
          'annotation-excerpt',
          (item.anchor.quote || item.anchor.text).slice(0, 140)
        );
        quote.dir = 'auto';
        row.append(jump, meta, quote);
        if (item.kind === 'note') {
          const note = element('div', 'annotation-note', item.body);
          note.dir = 'auto';
          row.append(note);
        }
        const actions = element('div', 'annotation-actions');
        const edit = element('button', '', 'Edit');
        edit.type = 'button';
        edit.onclick = () => openDialog(item.kind, null, item);
        const remove = element('button', '', 'Delete');
        remove.type = 'button';
        remove.setAttribute('aria-label', `Delete ${item.label}`);
        remove.onclick = () => native()?.deleteAnnotation(current().path, item.id);
        actions.append(edit, remove);
        row.append(actions);
        container.append(row);
      }
    }

    function refresh(decorate = true) {
      const doc = current(),
        entry = record();
      $('star-document').disabled = !persistent();
      $('star-document').setAttribute('aria-pressed', String(Boolean(entry?.starred)));
      $('star-document').querySelector('span').textContent = entry?.starred
        ? 'Starred'
        : 'Star document';
      $('star-document').title = entry?.starred ? 'Unstar this document' : 'Star this document';
      $('add-mark').disabled = $('add-note').disabled = !canAdd();
      ReaderOpenAPI.contentRoot(article)
        .querySelectorAll('.annotation-tools button')
        .forEach((button) => {
          button.disabled = !canAdd();
        });
      $('annotations-button').disabled = !doc;
      $('annotation-count').textContent = items().length;
      $('resume-reading').disabled = !entry?.resumeId;
      const resume = items().find((item) => item.id === entry?.resumeId);
      $('memory-status').textContent = !doc
        ? ''
        : !available
          ? 'Reading library unavailable'
          : !persistent()
            ? 'Save this file to keep marks and notes'
            : doc.dirty
              ? 'Save changes before adding marks or notes'
              : resume
                ? `Continue: ${resume.label}`
                : 'Your reading places stay with this document';
      if (decorate) {
        libraryList();
        annotationList();
        ReaderAnnotations.decorate(blocks, items(), entry?.resumeId);
      }
    }

    function openDialog(kind, block = null, item = null) {
      if (document.querySelector('dialog[open]')) return;
      if (!item && !canAdd()) {
        toast('Save the document and wait for the preview before adding a mark or note.', true);
        return;
      }
      const doc = current();
      if (!doc) return;
      const anchor =
        item?.anchor || ReaderAnnotations.capture(blocks, scroller, block, doc.fingerprint || '');
      if (!anchor) return;
      dialogContext = {
        id: doc.id,
        path: doc.path,
        source: sourceOf(doc),
        kind,
        anchor,
        itemId: item?.id || '',
        focus: document.activeElement,
      };
      const noun = kind === 'note' ? 'note' : 'mark';
      $('annotation-dialog-title').textContent = `${item ? 'Edit' : 'Add'} ${noun}`;
      $('annotation-name').value =
        item?.label ||
        `${kind === 'note' ? 'Note' : 'Mark'} ${items().filter((i) => i.kind === kind).length + 1}`;
      $('annotation-body').value = item?.body || '';
      $('annotation-body').required = kind === 'note';
      $('annotation-body-group').hidden = kind !== 'note';
      $('annotation-context').textContent = anchor.quote || anchor.text;
      $('annotation-error').hidden = true;
      $('annotation-save').disabled = false;
      $('annotation-save').textContent = `Save ${noun}`;
      $('annotations-panel').hidden = true;
      $('annotations-button').setAttribute('aria-expanded', 'false');
      $('annotation-dialog').showModal();
      if (kind === 'note') $('annotation-body').focus();
      else {
        $('annotation-name').focus();
        $('annotation-name').select();
      }
    }

    function scrollIntent() {
      if (
        !intent ||
        intent.doc !== current()?.id ||
        Date.now() > intent.until ||
        !intent.block.element.isConnected
      ) {
        intent = null;
        return;
      }
      const target =
        intent.block.element.getBoundingClientRect().top -
        scroller.getBoundingClientRect().top +
        scroller.scrollTop -
        40;
      scroller.scrollTo({ top: Math.max(0, target), behavior: 'instant' });
    }
    function go(identifier, quiet = false) {
      const item = items().find((item) => item.id === identifier);
      if (!item) return;
      const { block, exact } = ReaderAnnotations.locate(blocks, item.anchor);
      if (!block) return;
      intent = { block, doc: current().id, until: Date.now() + 3000 };
      scrollIntent();
      requestAnimationFrame(scrollIntent);
      document.fonts.ready.then(scrollIntent);
      block.element.classList.remove('annotation-flash');
      requestAnimationFrame(() => {
        if (block.element.isConnected) block.element.classList.add('annotation-flash');
      });
      if (!quiet) {
        native()?.resumeAnnotation(current().path, item.id);
        if (!exact)
          toast('The original text changed. Showing the nearest available location.', true);
      }
      if (item.kind === 'note' && !quiet) {
        $('annotations-panel').hidden = false;
        $('annotations-button').setAttribute('aria-expanded', 'true');
        $('annotation-list')
          .querySelector(`[data-id="${item.id}"]`)
          ?.scrollIntoView({ block: 'nearest' });
      }
    }
    function resume(quiet = false) {
      go(record()?.resumeId, quiet);
    }

    $('library-all').onclick = () => {
      starredOnly = false;
      libraryList();
    };
    $('library-starred').onclick = () => {
      starredOnly = true;
      libraryList();
    };
    $('star-document').onclick = () => {
      if (persistent()) native()?.starDocument(current().path, !record()?.starred);
    };
    for (const id of ['add-mark', 'add-note'])
      $(id).addEventListener('mousedown', (event) => event.preventDefault());
    $('add-mark').onclick = () => openDialog('mark');
    $('add-note').onclick = () => openDialog('note');
    $('resume-reading').onclick = () => resume();
    $('annotations-button').onclick = () => {
      $('annotations-panel').hidden = !$('annotations-panel').hidden;
      $('annotations-button').setAttribute('aria-expanded', String(!$('annotations-panel').hidden));
    };
    $('annotation-cancel').onclick = () => $('annotation-dialog').close();
    $('annotation-dialog').addEventListener('close', () => {
      // A queued close event may arrive after another annotation is opened.
      if ($('annotation-dialog').open) return;
      if (dialogContext?.focus?.isConnected) dialogContext.focus.focus({ preventScroll: true });
      dialogContext = null;
    });
    $('annotation-form').onsubmit = (event) => {
      event.preventDefault();
      const context = dialogContext,
        doc = current();
      if (!context || !doc) return;
      if (
        doc.id !== context.id ||
        doc.path !== context.path ||
        (!context.itemId && sourceOf(doc) !== context.source)
      ) {
        $('annotation-error').textContent =
          'The document changed. Cancel and select a location again.';
        $('annotation-error').hidden = false;
        return;
      }
      $('annotation-save').disabled = true;
      native()?.saveAnnotation(
        doc.id,
        sourceOf(doc),
        JSON.stringify({
          id: context.itemId,
          kind: context.kind,
          anchor: context.anchor,
          label: $('annotation-name').value,
          body: $('annotation-body').value,
        }),
        (success) => {
          if (dialogContext !== context) return;
          $('annotation-save').disabled = false;
          if (success) {
            $('annotation-dialog').close();
            toast(context.kind === 'note' ? 'Note saved' : 'Mark saved');
          } else {
            $('annotation-error').textContent =
              'Could not save. Check the name and note, then try again.';
            $('annotation-error').hidden = false;
          }
        }
      );
    };
    document.addEventListener('click', (event) => {
      if (
        !event
          .composedPath()
          .some((node) => node.matches?.('.annotations-anchor,.annotation-badge'))
      ) {
        $('annotations-panel').hidden = true;
        $('annotations-button').setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (
        event.key === 'Escape' &&
        !$('annotations-panel').hidden &&
        !document.querySelector('dialog[open]')
      ) {
        event.preventDefault();
        $('annotations-panel').hidden = true;
        $('annotations-button').setAttribute('aria-expanded', 'false');
      }
    });
    for (const name of ['wheel', 'touchstart', 'pointerdown', 'keydown'])
      document.addEventListener(
        name,
        () => {
          intent = null;
        },
        { passive: true }
      );
    return {
      entry: (path) => entries.get(path),
      visibleEntries,
      orderedDocuments,
      refresh,
      resume,
      add: openDialog,
      resize: scrollIntent,
      mount() {
        intent = null;
        blocks = ReaderAnnotations.prepare(article, openDialog, go);
        refresh();
      },
      receive(raw) {
        const value = JSON.parse(raw);
        available = value.available;
        categories.receive(value.categories, available);
        entries = new Map(value.entries.map((entry) => [entry.path, entry]));
        refresh();
      },
      changed(firstVisit) {
        $('annotations-panel').hidden = true;
        $('annotations-button').setAttribute('aria-expanded', 'false');
        refresh();
        if (firstVisit) resume(true);
      },
    };
  }
  window.ReaderLibrary = { create };
})();
