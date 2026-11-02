/* Render file tabs and translate their gestures into application callbacks. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({
    documents,
    current,
    native,
    sourceOf,
    showDocument,
    closeDocument,
    detachDocument,
    icon,
    formatNumber,
  }) {
    function renderFiles() {
      $('file-list').replaceChildren();
      $('file-count').textContent = formatNumber(documents.size);
      for (const doc of documents.values()) {
        const row = document.createElement('div');
        row.className = `file-item${doc.id === current() ? ' active' : ''}`;
        const select = document.createElement('button');
        select.className = 'file-select';
        select.title = doc.path;
        select.innerHTML = icon('file');
        select.setAttribute('aria-current', doc.id === current() ? 'page' : 'false');
        const name = document.createElement('span');
        name.dir = 'auto';
        name.textContent = doc.name;
        select.append(name);
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
        let pointer;
        select.addEventListener('pointerdown', (event) => {
          if (event.button !== 0 || !native() || doc.moving) return;
          pointer = { x: event.clientX, y: event.clientY };
          select.setPointerCapture(event.pointerId);
        });
        select.addEventListener('pointerup', () => {
          pointer = null;
        });
        select.addEventListener('pointercancel', () => {
          pointer = null;
        });
        select.addEventListener('pointermove', (event) => {
          if (
            !pointer ||
            !(event.buttons & 1) ||
            Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) < 10
          )
            return;
          pointer = null;
          select.releasePointerCapture(event.pointerId);
          document.body.classList.add('tab-dragging');
          native().startTabDrag(doc.id, sourceOf(doc), '{}');
        });
        row.append(select, detach, close);
        $('file-list').append(row);
      }
    }

    return { render: renderFiles };
  }
  window.ReaderFileList = { create };
})();
