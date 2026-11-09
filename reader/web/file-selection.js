/* Selection and in-sidebar drag/drop; single-tab drags can still leave the window. */
(() => {
  'use strict';
  function create({ items, entry, categories, startTabDrag }) {
    let scope = null,
      selected = new Set(),
      drag = null,
      suppressClick = false;
    const key = (item) => item.id || item.path;
    const ghost = document.createElement('div');
    ghost.className = 'file-drag-label';
    ghost.hidden = true;
    document.body.append(ghost);
    function current() {
      const valid = (scope ? items(scope) : []).filter((item) => selected.has(key(item)));
      selected = new Set(valid.map(key));
      return valid;
    }
    function refresh() {
      current();
      document.querySelectorAll('[data-selection-key]').forEach((row) => {
        const active =
          row.dataset.selectionScope === scope && selected.has(row.dataset.selectionKey);
        row.classList.toggle('selected', active);
        row
          .querySelector('.file-select,.library-open')
          ?.setAttribute('aria-pressed', String(active));
      });
    }
    function choose(target, area, extend = false, toggle = false) {
      if (scope !== area || !extend) selected.clear();
      scope = area;
      if (toggle && selected.has(key(target))) selected.delete(key(target));
      else selected.add(key(target));
      refresh();
    }
    function selectAll(area) {
      scope = area;
      selected = new Set(items(area).map(key));
      refresh();
    }
    function finish() {
      const previous = drag;
      drag = null;
      ghost.hidden = true;
      document.body.classList.remove('dragging-files');
      document
        .querySelectorAll('.category-drop-target')
        .forEach((node) => node.classList.remove('category-drop-target'));
      if (previous?.select.hasPointerCapture(previous.pointer))
        previous.select.releasePointerCapture(previous.pointer);
      return previous;
    }
    function bind(row, select, target, area) {
      row.dataset.selectionKey = key(target);
      row.dataset.selectionScope = area;
      row.classList.toggle('selected', scope === area && selected.has(key(target)));
      select.setAttribute('aria-pressed', String(row.classList.contains('selected')));
      select.addEventListener(
        'click',
        (event) => {
          if (suppressClick) {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
          }
          const multiple = event.ctrlKey || event.metaKey;
          choose(target, area, multiple, multiple);
          if (multiple) {
            event.preventDefault();
            event.stopImmediatePropagation();
          }
        },
        true
      );
      row.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
          event.preventDefault();
          event.stopPropagation();
          selectAll(area);
        }
      });
      select.addEventListener('pointerdown', (event) => {
        if (event.button !== 0 || drag) return;
        drag = {
          select,
          target,
          scope: area,
          pointer: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          active: false,
        };
        select.setPointerCapture(event.pointerId);
      });
      select.addEventListener('pointermove', (event) => {
        if (!drag || drag.select !== select || drag.pointer !== event.pointerId) return;
        if (!(event.buttons & 1)) {
          finish();
          return;
        }
        if (!drag.active && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 10) return;
        if (!drag.active) {
          if (scope !== area || !selected.has(key(target)))
            choose(target, area, event.ctrlKey || event.metaKey);
          drag.active = true;
          document.body.classList.add('dragging-files');
        }
        const chosen = current(),
          sidebar = document.getElementById('sidebar-panel').getBoundingClientRect();
        if (
          area === 'files' &&
          chosen.length === 1 &&
          !chosen[0].moving &&
          (event.clientX > sidebar.right + 12 ||
            event.clientX < sidebar.left - 12 ||
            event.clientY < 0 ||
            event.clientY > innerHeight)
        ) {
          const id = chosen[0].id;
          finish();
          suppressClick = true;
          startTabDrag(id);
          setTimeout(() => {
            suppressClick = false;
          }, 150);
          return;
        }
        const destination = document
          .elementFromPoint(event.clientX, event.clientY)
          ?.closest('.file-category');
        document
          .querySelectorAll('.category-drop-target')
          .forEach((node) => node.classList.remove('category-drop-target'));
        const eligible =
          chosen.length && chosen.every((item) => item.path && entry(item.path) && !item.moving);
        drag.destination = eligible ? destination : null;
        drag.destination?.classList.add('category-drop-target');
        ghost.textContent = eligible
          ? `${chosen.length} file${chosen.length === 1 ? '' : 's'}${destination ? ' → ' + destination.querySelector('.category-name').textContent : ''}`
          : 'Save files before categorizing';
        ghost.hidden = false;
        ghost.style.left = `${Math.min(innerWidth - 220, event.clientX + 16)}px`;
        ghost.style.top = `${event.clientY + 14}px`;
        const list = document
          .elementFromPoint(event.clientX, event.clientY)
          ?.closest('#file-list,#library-list');
        if (list) {
          const bounds = list.getBoundingClientRect();
          if (event.clientY > bounds.bottom - 24) list.scrollTop += 14;
          else if (event.clientY < bounds.top + 24) list.scrollTop -= 14;
        }
      });
      select.addEventListener('pointerup', (event) => {
        if (drag?.select !== select || drag.pointer !== event.pointerId) return;
        const previous = finish();
        if (!previous?.active) return;
        suppressClick = true;
        if (previous.destination)
          categories.move(
            current().map((item) => item.path),
            previous.destination.dataset.categoryId
          );
        setTimeout(() => {
          suppressClick = false;
        }, 150);
      });
      for (const name of ['pointercancel', 'lostpointercapture'])
        select.addEventListener(name, () => {
          if (drag?.select === select) finish();
        });
    }
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape' && drag?.active) {
          event.preventDefault();
          event.stopImmediatePropagation();
          suppressClick = true;
          finish();
          setTimeout(() => {
            suppressClick = false;
          }, 150);
        }
      },
      true
    );
    window.addEventListener('blur', finish);
    return {
      bind,
      refresh,
      selectAll,
      forMenu(target, area) {
        if (scope !== area || !selected.has(key(target))) choose(target, area);
        return current();
      },
    };
  }
  window.ReaderFileSelection = { create };
})();
