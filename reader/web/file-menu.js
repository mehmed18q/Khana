/* Context actions for single files and Ctrl-selected groups. */
(() => {
  'use strict';
  function create({
    documents,
    native,
    libraryEntry,
    orderedEntries,
    orderedDocuments,
    showDocument,
    closeDocument,
    closeDocuments,
    detachDocument,
    saveDocument,
    splitDocuments,
    toast,
    menu,
    categories,
    selection,
  }) {
    function show(event, target, select, scope, keyboard = false) {
      const chosen = selection.forMenu(target, scope);
      if (!chosen.length) return;
      const actions = [],
        bridge = native();
      const item = (id, label, run, disabled = false, title = '') =>
        actions.push({ id, label, run, disabled, title });
      const separator = () => actions.push(null);
      const docOf = (item) =>
        item.id
          ? documents.get(item.id)
          : [...documents.values()].find((doc) => doc.path === item.path);
      const paths = chosen.map((item) => item.path).filter(Boolean),
        records = paths.map(libraryEntry),
        allSaved = paths.length === chosen.length && records.every(Boolean),
        onDisk = paths.length === chosen.length && records.every((entry) => !entry?.missing),
        docs = chosen.map(docOf).filter(Boolean),
        busy = docs.some((doc) => doc.moving || doc.closing);
      const copyFiles = (cut) =>
        bridge.copyFiles(JSON.stringify(paths), cut, (success) => {
          if (success)
            toast(
              cut
                ? 'Files cut. Paste in a folder to move them.'
                : 'Files copied. Paste in a folder.'
            );
        });
      if (chosen.length > 1) {
        item(
          'open',
          `Open ${chosen.length} files`,
          () =>
            chosen.forEach((item) => {
              const doc = docOf(item);
              if (doc) showDocument(doc.id);
              else bridge?.openLibrary(item.path);
            }),
          busy || !onDisk
        );
        separator();
        item('copy', `Copy ${chosen.length} files`, () => copyFiles(false), !bridge || !onDisk);
        item(
          'cut',
          `Cut ${chosen.length} files`,
          () => copyFiles(true),
          !bridge || !onDisk || busy
        );
        item(
          'copy-path',
          'Copy paths',
          () => {
            bridge.copyText(paths.join('\n'));
            toast('Paths copied');
          },
          !bridge || paths.length !== chosen.length
        );
        item(
          'move-category',
          'Move to category…',
          () => categories.choose(paths),
          !bridge || !allSaved || busy
        );
        separator();
        for (const [id, flag, label] of [
          ['star', 'starred', 'Star'],
          ['pin', 'pinned', 'Pin'],
        ]) {
          const enabled = records.every((entry) => entry?.[flag]);
          item(
            id,
            `${enabled ? 'Un' + label.toLowerCase() : label} selected files`,
            () =>
              bridge.setDocumentFlags(JSON.stringify(paths), flag, !enabled, (message) => {
                if (message) toast(message, true);
              }),
            !bridge || !allSaved
          );
        }
        separator();
        item('rename', 'Rename file…', () => {}, true, 'Select one file to rename');
      } else {
        const doc = docs[0],
          path = paths[0] || '',
          entry = records[0];
        item(
          'open',
          'Open',
          () => (doc ? showDocument(doc.id) : bridge?.openLibrary(path)),
          busy || (!doc && !onDisk)
        );
        item(
          'new-window',
          'Open in new window',
          () => (doc ? detachDocument(doc.id) : bridge?.openLibraryWindow(path)),
          !bridge || busy || (!doc && !onDisk),
          'Move an open tab with its unsaved changes'
        );
        separator();
        item(
          'copy',
          'Copy file',
          () => copyFiles(false),
          !bridge || !onDisk,
          'Copies the saved file on disk'
        );
        item(
          'cut',
          'Cut file',
          () => copyFiles(true),
          !bridge || !onDisk || busy,
          'Moves the saved file when pasted into a folder'
        );
        item(
          'copy-path',
          'Copy path',
          () => {
            bridge.copyText(path);
            toast('Path copied');
          },
          !bridge || !path
        );
        item(
          'copy-name',
          'Copy file name',
          () => {
            bridge.copyText(chosen[0].name);
            toast('File name copied');
          },
          !bridge
        );
        item(
          'open-folder',
          'Open containing folder',
          () => bridge?.openFileFolder(path),
          !bridge || !path
        );
        item(
          'rename',
          'Rename file…',
          () => categories.renameFile(path, chosen[0].name),
          !bridge || !entry || !onDisk || busy
        );
        item(
          'move-category',
          'Move to category…',
          () => categories.choose([path]),
          !bridge || !entry || busy,
          !entry ? 'Save this document first' : ''
        );
        separator();
        item(
          'star',
          entry?.starred ? 'Unstar' : 'Star',
          () => bridge?.starDocument(path, !entry.starred),
          !bridge || !entry
        );
        item(
          'pin',
          entry?.pinned ? 'Unpin' : 'Pin to top',
          () => bridge?.pinDocument(path, !entry.pinned),
          !bridge || !entry
        );
        const peers = (
            scope === 'files'
              ? orderedDocuments()
                  .map((item) => libraryEntry(item.path))
                  .filter(Boolean)
              : orderedEntries()
          ).filter(
            (item) => item.pinned === entry?.pinned && item.categoryId === entry?.categoryId
          ),
          index = peers.findIndex((item) => item.path === path),
          previous = peers[index - 1],
          next = index < 0 ? null : peers[index + 1];
        item(
          'move-up',
          'Move higher',
          () => bridge?.moveDocument(path, previous.path, true),
          !bridge || !previous
        );
        item(
          'move-down',
          'Move lower',
          () => bridge?.moveDocument(path, next.path, false),
          !bridge || !next
        );
        if (doc) {
          separator();
          item('save', 'Save', () => saveDocument(false, doc.id), !bridge || busy || doc.saving);
          item(
            'save-as',
            'Save as…',
            () => saveDocument(true, doc.id),
            !bridge || busy || doc.saving
          );
        }
      }
      separator();
      for (const [mode, label] of [
        ['columns', 'Split vertically'],
        ['rows', 'Split horizontally'],
        ['grid', 'Four panes'],
      ])
        item(
          'layout-' + mode,
          label,
          () => splitDocuments(chosen, mode),
          busy ||
            (!onDisk && docs.length !== chosen.length) ||
            (chosen.length > 1 && docs.length !== chosen.length)
        );
      item('layout-single', 'Single page', () => splitDocuments([], 'single'));
      separator();
      item(
        'close',
        chosen.length > 1
          ? `Close ${docs.length} open file${docs.length === 1 ? '' : 's'}`
          : 'Close',
        () =>
          chosen.length > 1 ? closeDocuments(docs.map((doc) => doc.id)) : closeDocument(docs[0].id),
        !docs.length || busy
      );
      if (chosen.length === 1 && records[0])
        item(
          'forget',
          'Remove from library',
          () => bridge?.forgetDocument(paths[0]),
          !bridge || docs.length > 0,
          docs.length ? 'Close this document first' : 'Keeps the source file'
        );
      menu.open(
        event,
        select,
        chosen.length > 1 ? `Actions for ${chosen.length} files` : `Actions for ${chosen[0].name}`,
        actions,
        keyboard
      );
    }
    return {
      bind(row, target, select) {
        const scope = target.id ? 'files' : 'library';
        selection.bind(row, select, target, scope);
        select.setAttribute('aria-haspopup', 'menu');
        select.setAttribute('aria-expanded', 'false');
        row.addEventListener('contextmenu', (event) =>
          show(event, target, select, scope, !event.clientX && !event.clientY)
        );
        row.addEventListener('keydown', (event) => {
          if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10'))
            show(event, target, select, scope, true);
        });
      },
    };
  }
  window.ReaderFileMenu = { create };
})();
