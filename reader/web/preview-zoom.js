/* Document magnification without changing the surrounding app or source editor. */
(() => {
  'use strict';
  function create({ article, scroller, beforeChange, afterChange, changed }) {
    const minus = document.getElementById('preview-zoom-out');
    const reset = document.getElementById('preview-zoom-reset');
    const output = document.getElementById('preview-zoom-value');
    const plus = document.getElementById('preview-zoom-in');
    let value = 100;
    const normalize = (input) =>
      Number.isFinite(Number(input)) ? Math.max(50, Math.min(300, Math.round(Number(input)))) : 100;

    function refresh() {
      // Keep the unscaled page width fixed to the preview viewport. Otherwise
      // CSS auto sizing fits images/PDF pages back into the box at every zoom.
      const css = getComputedStyle(scroller);
      article.style.width = `${Math.max(0, scroller.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight))}px`;
      article.style.zoom = value / 100;
      output.textContent = `${value}%`;
      minus.disabled = article.hidden || value <= 50;
      plus.disabled = article.hidden || value >= 300;
      reset.disabled = article.hidden;
    }

    function set(input, point, save = true) {
      const next = normalize(input);
      if (next === value) {
        refresh();
        return;
      }
      const viewport = scroller.getBoundingClientRect();
      const x = point?.x ?? viewport.left + scroller.clientWidth / 2;
      const y = point?.y ?? viewport.top + scroller.clientHeight / 2;
      const old = article.getBoundingClientRect();
      const logical = { x: (x - old.left) / (value / 100), y: (y - old.top) / (value / 100) };
      beforeChange();
      value = next;
      refresh();
      const rect = article.getBoundingClientRect();
      // Keep the part being read under the pointer, including horizontal pan
      // when a magnified page is wider than its viewport.
      scroller.scrollBy({
        left: rect.left + (logical.x * value) / 100 - x,
        top: rect.top + (logical.y * value) / 100 - y,
        behavior: 'instant',
      });
      afterChange();
      if (save) changed(value);
    }

    const step = (direction, point) => {
      if (!article.hidden) set(value + direction * 10, point);
    };
    minus.onclick = () => step(-1);
    plus.onclick = () => step(1);
    reset.onclick = () => set(100);

    // Chromium's normal Ctrl+wheel zoom affects the whole WebEngine page.
    // Cancel it throughout the UI; magnify only when pointing at the preview.
    document.addEventListener(
      'wheel',
      (event) => {
        if (!event.ctrlKey) return;
        event.preventDefault();
        if (
          !event.target.closest('#reading-scroll') ||
          document.querySelector('dialog[open]') ||
          !event.deltaY
        )
          return;
        step(event.deltaY < 0 ? 1 : -1, { x: event.clientX, y: event.clientY });
      },
      { passive: false, capture: true }
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (!(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing) return;
        const key = event.code || event.key;
        const direction = ['Equal', 'NumpadAdd', '+', '='].includes(key)
          ? 1
          : ['Minus', 'NumpadSubtract', '-'].includes(key)
            ? -1
            : 0;
        const isReset = ['Digit0', 'Numpad0', '0'].includes(key);
        if (!direction && !isReset) return;
        event.preventDefault();
        if (document.querySelector('dialog[open]') || article.hidden) return;
        if (isReset) set(100);
        else step(direction);
      },
      true
    );
    let resizeFrame;
    new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(refresh);
    }).observe(scroller);
    return { refresh, restore: (input) => set(input, null, false) };
  }
  window.ReaderPreviewZoom = { create };
})();
