/* Keyboard-accessible icon menus backed by the existing form controls. */
(() => {
  'use strict';
  const chevron = '<svg aria-hidden="true"><use href="#i-chevron"/></svg>';
  const globe =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 6.5h14M5 17.5h14"/></svg>';
  function flag(language) {
    const shapes =
      language === 'fa'
        ? '<path fill="#239f40" d="M0 0h30v6H0z"/><path fill="#fff" d="M0 6h30v6H0z"/><path fill="#da0000" d="M0 12h30v6H0z"/><text x="15" y="11.5" text-anchor="middle" fill="#da0000" font-size="8">☫</text>'
        : '<path fill="#fff" d="M0 0h30v18H0z"/><path stroke="#b22234" stroke-width="1.4" d="M0 .7h30M0 3.5h30M0 6.3h30M0 9.1h30M0 11.9h30M0 14.7h30M0 17.5h30"/><path fill="#3c3b6e" d="M0 0h13v10H0z"/><path stroke="#fff" stroke-width="1" stroke-dasharray="1 2" d="M2 2h10M2 4h10M2 6h10M2 8h10"/>';
    return `<svg class="language-flag" viewBox="0 0 30 18" aria-hidden="true">${shapes}</svg>`;
  }
  function create() {
    for (const id of ['ui-language', 'new-format']) {
      const select = document.getElementById(id),
        language = id === 'ui-language',
        trigger = document.createElement('button'),
        menu = document.createElement('div');
      select.hidden = true;
      trigger.type = 'button';
      trigger.id = `${id}-button`;
      trigger.className = language
        ? 'icon-button picker-button'
        : 'format-picker-button picker-button';
      trigger.setAttribute('aria-label', language ? 'Application language' : 'New document format');
      trigger.setAttribute('aria-haspopup', 'listbox');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.setAttribute('aria-controls', `${id}-menu`);
      trigger.title = language ? 'Application language' : 'New document format';
      menu.id = `${id}-menu`;
      menu.className = 'picker-menu';
      menu.popover = 'auto';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', trigger.getAttribute('aria-label'));
      select.after(trigger);
      document.body.append(menu);
      const items = [...select.options].map((option) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('role', 'option');
        button.dataset.value = option.value;
        button.tabIndex = -1;
        button.innerHTML = language
          ? flag(option.value)
          : ReaderFileIcons.markup({ format: option.value });
        const label = document.createElement('span');
        label.textContent = language ? option.textContent : option.value;
        button.append(label);
        button.onclick = () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          render();
          menu.hidePopover();
          trigger.focus({ preventScroll: true });
        };
        menu.append(button);
        return button;
      });
      function render() {
        const selected = select.selectedOptions[0];
        trigger.innerHTML = language ? globe : ReaderFileIcons.markup({ format: select.value });
        if (!language) {
          const label = document.createElement('span');
          label.textContent = selected.textContent;
          trigger.append(label);
          trigger.insertAdjacentHTML('beforeend', chevron);
        }
        for (const item of items)
          item.setAttribute('aria-selected', String(item.dataset.value === select.value));
      }
      function open() {
        render();
        menu.showPopover();
        const rect = trigger.getBoundingClientRect(),
          rtl = document.documentElement.dir === 'rtl';
        menu.style.left = `${Math.max(8, Math.min(innerWidth - menu.offsetWidth - 8, rtl ? rect.right - menu.offsetWidth : rect.left))}px`;
        menu.style.top = `${Math.max(8, Math.min(innerHeight - menu.offsetHeight - 8, rect.bottom + 5))}px`;
        items.find((item) => item.dataset.value === select.value)?.focus();
      }
      trigger.onclick = () => (menu.matches(':popover-open') ? menu.hidePopover() : open());
      trigger.onkeydown = (event) => {
        if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
          event.preventDefault();
          open();
        }
      };
      menu.addEventListener('toggle', (event) =>
        trigger.setAttribute('aria-expanded', String(event.newState === 'open'))
      );
      menu.onkeydown = (event) => {
        const index = items.indexOf(document.activeElement),
          next = {
            ArrowDown: (index + 1) % items.length,
            ArrowUp: (index - 1 + items.length) % items.length,
            Home: 0,
            End: items.length - 1,
          }[event.key];
        if (next !== undefined) {
          event.preventDefault();
          event.stopPropagation();
          items[next].focus();
        }
        if (event.key === 'Escape' || event.key === 'Tab') {
          menu.hidePopover();
          if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            trigger.focus();
          }
        }
      };
      select.addEventListener('change', render);
      render();
      window.addEventListener('resize', () => {
        if (menu.matches(':popover-open')) menu.hidePopover();
      });
    }
  }
  window.ReaderPickers = { create };
})();
