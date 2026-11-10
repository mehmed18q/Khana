/* Compact the reading controls without changing the window or sidebar state. */
(() => {
  'use strict';
  function create({ changed, beforeChange, afterChange, native }) {
    const collapse = document.getElementById('header-collapse'),
      expand = document.getElementById('header-expand');
    function restore(value, focus = false) {
      const collapsed = value === true;
      beforeChange();
      document.body.classList.toggle('header-collapsed', collapsed);
      collapse.setAttribute('aria-expanded', String(!collapsed));
      expand.setAttribute('aria-expanded', String(!collapsed));
      if (focus) (collapsed ? expand : collapse).focus({ preventScroll: true });
      requestAnimationFrame(afterChange);
    }
    collapse.onclick = () => {
      restore(true, true);
      changed(true);
    };
    expand.onclick = () => {
      restore(false, true);
      changed(false);
    };
    let lastPath;
    function showPath(doc) {
      const path = doc?.path || '';
      if (path === lastPath) return;
      lastPath = path;
      const nav = document.getElementById('document-path'),
        folders = document.getElementById('document-folders');
      folders.replaceChildren();
      nav.hidden = !path;
      if (!path) return;
      for (const [index, folder] of (doc.folders || []).entries()) {
        if (index) {
          const separator = document.createElement('span');
          separator.textContent = '›';
          separator.className = 'path-separator';
          separator.setAttribute('aria-hidden', 'true');
          folders.append(separator);
        }
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = folder.name;
        button.dir = 'auto';
        button.title = folder.path;
        button.onclick = () => native()?.openDocumentFolder(doc.id, folder.path);
        folders.append(button);
      }
      requestAnimationFrame(() => {
        folders.scrollLeft = folders.scrollWidth;
      });
    }
    return { restore, showPath };
  }
  window.ReaderHeader = { create };
})();
