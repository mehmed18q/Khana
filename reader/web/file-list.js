/* Render file tabs and translate their gestures into application callbacks. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({
    documents,
    current,
    showDocument,
    closeDocument,
    detachDocument,
    icon,
    formatNumber,
    bindFileMenu,
    orderedDocuments,
    libraryEntry,
    categories,
  }) {
    function renderFiles() {
      $('file-count').textContent = formatNumber(documents.size);
      categories.render(
        $('file-list'),
        orderedDocuments(),
        (doc) => libraryEntry(doc.path)?.categoryId,
        (doc) => {
          const row = document.createElement('div');
          row.className = `file-item${doc.id === current() ? ' active' : ''}`;
          row.dataset.id = doc.id;
          const select = document.createElement('button');
          select.className = 'file-select';
          select.title = doc.path;
          select.innerHTML = ReaderFileIcons.markup(doc);
          select.setAttribute('aria-current', doc.id === current() ? 'page' : 'false');
          const name = document.createElement('span');
          name.className = 'file-name';
          name.dir = 'auto';
          name.textContent = doc.name;
          select.append(name);
          const entry = libraryEntry(doc.path);
          if (entry?.pinned || entry?.starred) {
            const badge = document.createElement('span');
            badge.className = 'file-priority';
            badge.innerHTML = entry.pinned ? icon('pin') : icon('star');
            badge.title = [entry.pinned && 'Pinned', entry.starred && 'Starred']
              .filter(Boolean)
              .join(' · ');
            badge.setAttribute('aria-label', badge.title);
            select.append(badge);
          }
          if (doc.dirty) {
            const dot = document.createElement('span');
            dot.className = 'file-dirty';
            dot.title = 'Unsaved changes';
            dot.setAttribute('aria-label', 'Unsaved changes');
            select.append(dot);
          }
          select.onclick = () => showDocument(doc.id);
          const close = document.createElement('button');
          close.className = 'file-close';
          close.innerHTML = icon('close');
          close.setAttribute('aria-label', `Close ${doc.name}`);
          close.disabled = Boolean(doc.moving);
          close.onclick = () => closeDocument(doc.id);
          const detach = document.createElement('button');
          detach.className = 'file-detach';
          detach.textContent = '↗';
          detach.title = 'Move tab to a new window';
          detach.setAttribute('aria-label', `Move ${doc.name} to a new window`);
          detach.disabled = Boolean(doc.moving);
          detach.onclick = () => detachDocument(doc.id);
          row.append(select, detach, close);
          bindFileMenu(row, { id: doc.id }, select);
          return row;
        },
        'files'
      );
    }

    return { render: renderFiles };
  }
  window.ReaderFileList = { create };
})();
