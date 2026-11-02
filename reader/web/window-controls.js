/* Native window gestures; only deliberate drags start a compositor move. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ native }) {
    $('fullscreen-button').onclick = () => native()?.toggleFullscreen();
    $('minimize-button').onclick = () => native()?.minimize();
    document.querySelectorAll('[data-window-drag]').forEach((region) => {
      let press = null;
      const isControl = (target) =>
        target.closest('button, input, select, textarea, a, [contenteditable], [role="button"]');
      const reset = () => {
        if (press && region.hasPointerCapture(press.id)) region.releasePointerCapture(press.id);
        press = null;
      };
      region.addEventListener('pointerdown', (event) => {
        if (event.button !== 0 || !event.isPrimary || isControl(event.target)) return;
        event.preventDefault();
        press = { id: event.pointerId, x: event.clientX, y: event.clientY };
        region.setPointerCapture(event.pointerId);
      });
      region.addEventListener('pointermove', (event) => {
        if (!press || event.pointerId !== press.id) return;
        if (!(event.buttons & 1)) {
          reset();
          return;
        }
        // A click (including the first half of a double-click) must not restore
        // fullscreen. Start a native move only after a deliberate drag.
        if (Math.hypot(event.clientX - press.x, event.clientY - press.y) < 8) return;
        reset();
        native()?.startWindowMove();
      });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((name) =>
        region.addEventListener(name, reset)
      );
      region.addEventListener('dblclick', (event) => {
        if (event.button !== 0 || isControl(event.target)) return;
        event.preventDefault();
        reset();
        native()?.toggleFullscreen();
      });
    });

    return {};
  }
  window.ReaderWindowControls = { create };
})();
