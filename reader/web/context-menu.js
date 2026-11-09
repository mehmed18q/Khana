/* One accessible menu shared by document and category actions. */
(() => {
  'use strict';
  function create() {
    const menu = document.createElement('div');
    menu.id = 'file-context-menu';
    menu.className = 'file-context-menu';
    menu.setAttribute('role', 'menu');
    menu.hidden = true;
    document.body.append(menu);
    let origin;
    function close(focus = false) {
      if (menu.hidden) return;
      menu.hidden = true;
      if (focus && origin?.isConnected) origin.focus({ preventScroll: true });
      origin?.setAttribute('aria-expanded', 'false');
      origin = null;
    }
    function open(event, anchor, title, actions, keyboard = false) {
      event.preventDefault();
      event.stopPropagation();
      close();
      origin = anchor;
      origin.setAttribute('aria-expanded', 'true');
      menu.setAttribute('aria-label', title);
      menu.replaceChildren();
      for (const action of actions) {
        const node = document.createElement(action ? 'button' : 'div');
        node.setAttribute('role', action ? 'menuitem' : 'separator');
        if (action) {
          node.type = 'button';
          node.tabIndex = -1;
          node.dataset.action = action.id;
          node.textContent = action.label;
          node.disabled = Boolean(action.disabled);
          node.title = action.title || '';
          node.onclick = () => {
            close(true);
            action.run();
          };
        }
        menu.append(node);
      }
      menu.hidden = false;
      const rect = anchor.getBoundingClientRect(),
        x = keyboard ? rect.left : event.clientX,
        y = keyboard ? rect.bottom : event.clientY;
      menu.style.left = `${Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8))}px`;
      menu.style.top = `${Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8))}px`;
      menu.querySelector('button:not(:disabled)')?.focus({ preventScroll: true });
    }
    menu.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' || event.key === 'Tab') {
        if (event.key === 'Escape') event.preventDefault();
        event.stopPropagation();
        close(true);
        return;
      }
      const items = [...menu.querySelectorAll('button:not(:disabled)')],
        index = items.indexOf(document.activeElement);
      const next = {
        ArrowDown: (index + 1) % items.length,
        ArrowUp: (index - 1 + items.length) % items.length,
        Home: 0,
        End: items.length - 1,
      }[event.key];
      if (next !== undefined) {
        event.preventDefault();
        event.stopPropagation();
        items[next]?.focus();
      }
    });
    for (const name of ['pointerdown', 'click', 'focusin', 'scroll'])
      document.addEventListener(
        name,
        (event) => {
          if (!menu.contains(event.target)) close();
        },
        true
      );
    window.addEventListener('resize', () => close());
    window.addEventListener('blur', () => close());
    return { open, close };
  }
  window.ReaderContextMenu = { create };
})();
