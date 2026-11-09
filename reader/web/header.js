/* Compact the reading controls without changing the window or sidebar state. */
(() => {
  'use strict';
  function create({ changed, beforeChange, afterChange }) {
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
    return { restore };
  }
  window.ReaderHeader = { create };
})();
