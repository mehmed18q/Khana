/* Persistent accordion sections with keyboard and pointer resizing. */
(() => {
  'use strict';
  const minimum = 48;
  function create({ changed }) {
    const container = document.getElementById('sidebar-sections');
    const sections = [...container.querySelectorAll('[data-sidebar-section]')].map((node) => ({
      id: node.dataset.sidebarSection,
      node,
      toggle: node.querySelector('.sidebar-toggle'),
      content: node.querySelector('.sidebar-section-content'),
      handle: node.querySelector('.sidebar-resizer'),
    }));
    let state = {},
      drag = null;
    const snapshot = () => Object.fromEntries(sections.map(({ id }) => [id, { ...state[id] }]));
    const opened = () => sections.filter((section) => state[section.id].open);
    const persist = () => changed(snapshot());

    function layout() {
      const visible = opened();
      sections.forEach((section) => {
        const open = state[section.id].open;
        section.toggle.setAttribute('aria-expanded', String(open));
        section.content.hidden = !open;
        section.handle.hidden = !open || section === visible.at(-1);
      });
      if (!container.clientHeight || !visible.length) return;
      const headers = sections.reduce((sum, section) => sum + section.toggle.offsetHeight, 0);
      const handles = visible.reduce((sum, section) => sum + section.handle.offsetHeight, 0);
      let available = Math.max(
        minimum * visible.length,
        container.clientHeight - headers - handles
      );
      let remaining = [...visible];
      const heights = new Map();
      // Reserve usable space for small sections before sharing the rest by weight.
      while (remaining.length) {
        const total = remaining.reduce((sum, section) => sum + state[section.id].weight, 0);
        const small = remaining.filter(
          (section) => (available * state[section.id].weight) / total < minimum
        );
        if (!small.length) {
          remaining.forEach((section) =>
            heights.set(section.id, (available * state[section.id].weight) / total)
          );
          break;
        }
        small.forEach((section) => heights.set(section.id, minimum));
        available -= minimum * small.length;
        remaining = remaining.filter((section) => !small.includes(section));
      }
      visible.forEach((section, index) => {
        section.content.style.height = `${heights.get(section.id)}px`;
        const next = visible[index + 1];
        if (!next) return;
        const max = Math.round(heights.get(section.id) + heights.get(next.id) - minimum);
        section.handle.setAttribute('aria-controls', `${section.content.id} ${next.content.id}`);
        section.handle.setAttribute('aria-valuemin', minimum);
        section.handle.setAttribute('aria-valuemax', max);
        section.handle.setAttribute('aria-valuenow', Math.round(heights.get(section.id)));
        section.handle.setAttribute(
          'aria-valuetext',
          `${Math.round(heights.get(section.id))} pixels`
        );
        section.handle.title = 'Drag to resize. Arrow keys adjust height; double-click to balance.';
      });
    }
    function sizing(section) {
      const visible = opened(),
        next = visible[visible.indexOf(section) + 1];
      if (!next || section.handle.hidden) return null;
      const heights = visible.map((item) => item.content.getBoundingClientRect().height);
      return {
        section,
        next,
        visible,
        heights,
        index: visible.indexOf(section),
        weight: visible.reduce((sum, item) => sum + state[item.id].weight, 0),
      };
    }
    function resize(context, height) {
      const heights = [...context.heights],
        index = context.index,
        combined = heights[index] + heights[index + 1];
      heights[index] = Math.max(minimum, Math.min(combined - minimum, height));
      heights[index + 1] = combined - heights[index];
      const total = heights.reduce((sum, value) => sum + value, 0);
      context.visible.forEach((section, i) => {
        state[section.id].weight = (context.weight * heights[i]) / total;
      });
      layout();
    }
    function finish(cancel = false) {
      if (!drag) return;
      const previous = drag;
      drag = null;
      if (cancel) state = previous.before;
      document.body.classList.remove('resizing-sidebar');
      if (previous.section.handle.hasPointerCapture(previous.pointer))
        previous.section.handle.releasePointerCapture(previous.pointer);
      layout();
      if (!cancel) persist();
    }
    sections.forEach((section) => {
      section.toggle.onclick = () => {
        finish(true);
        state[section.id].open = !state[section.id].open;
        layout();
        persist();
      };
      section.handle.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        const context = sizing(section);
        if (!context) return;
        event.preventDefault();
        section.handle.focus();
        drag = { ...context, before: snapshot(), y: event.clientY, pointer: event.pointerId };
        section.handle.setPointerCapture(event.pointerId);
        document.body.classList.add('resizing-sidebar');
      });
      section.handle.addEventListener('pointermove', (event) => {
        if (drag?.section === section && drag.pointer === event.pointerId)
          resize(drag, drag.heights[drag.index] + event.clientY - drag.y);
      });
      section.handle.addEventListener('pointerup', () => finish());
      section.handle.addEventListener('pointercancel', () => finish(true));
      section.handle.addEventListener('lostpointercapture', () => finish(true));
      section.handle.addEventListener('dblclick', () => {
        const context = sizing(section);
        if (!context) return;
        resize(context, (context.heights[context.index] + context.heights[context.index + 1]) / 2);
        persist();
      });
      section.handle.addEventListener('keydown', (event) => {
        const context = sizing(section);
        if (!context) return;
        const delta = event.shiftKey ? 48 : 16,
          height = context.heights[context.index];
        const target = {
          ArrowUp: height - delta,
          ArrowDown: height + delta,
          Home: minimum,
          End: height + context.heights[context.index + 1] - minimum,
        }[event.key];
        if (target === undefined) return;
        event.preventDefault();
        resize(context, target);
        persist();
      });
    });
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape' && drag) {
          event.preventDefault();
          finish(true);
        }
      },
      true
    );
    window.addEventListener('blur', () => finish(true));
    let resizeFrame;
    new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        finish(true);
        layout();
      });
    }).observe(container);
    function restore(value) {
      finish(true);
      state = Object.fromEntries(
        sections.map(({ id }) => {
          const saved = value?.[id],
            weight = Number(saved?.weight);
          return [
            id,
            {
              open: saved?.open !== false,
              weight:
                Number.isFinite(weight) && weight > 0 ? Math.max(0.01, Math.min(100, weight)) : 1,
            },
          ];
        })
      );
      layout();
    }
    restore();
    return { restore, snapshot };
  }
  window.ReaderSidebar = { create };
})();
