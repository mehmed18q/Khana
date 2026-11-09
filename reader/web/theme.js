/* Keep the saved theme choice separate from the effective system appearance. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const palettes = ['forest', 'ocean', 'violet', 'rose', 'amber', 'slate'];
  function create({ settings, changed, systemChanged }) {
    const media = matchMedia('(prefers-color-scheme: dark)');
    let system = media.matches ? 'dark' : 'light',
      nativeSystem = false;
    const panel = $('theme-panel'),
      trigger = $('theme-settings-button');
    const effective = () => (settings().theme === 'auto' ? system : settings().theme);
    function close(focus = false) {
      panel.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      if (focus) trigger.focus();
    }
    function apply() {
      const mode = settings().theme,
        current = effective();
      document.body.dataset.theme = current;
      document.body.dataset.palette = palettes.includes(settings().palette)
        ? settings().palette
        : 'forest';
      document.documentElement.style.colorScheme = current;
      document.querySelectorAll('[data-theme-choice]').forEach((button) => {
        button.setAttribute('aria-pressed', String(button.dataset.themeChoice === mode));
      });
      document.querySelectorAll('[data-palette-choice]').forEach((button) => {
        button.setAttribute(
          'aria-pressed',
          String(button.dataset.paletteChoice === document.body.dataset.palette)
        );
      });
      $('theme-system-status').textContent =
        `System appearance: ${system === 'dark' ? 'Dark' : 'Light'}`;
      $('theme-button').innerHTML =
        `<svg aria-hidden="true"><use href="#i-${current === 'dark' ? 'sun' : 'moon'}"/></svg>`;
      $('theme-button').title = $('theme-button').ariaLabel =
        current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    }
    document.querySelectorAll('[data-theme-choice]').forEach((button) => {
      button.onclick = () => changed({ theme: button.dataset.themeChoice });
    });
    document.querySelectorAll('[data-palette-choice]').forEach((button) => {
      button.onclick = () => changed({ palette: button.dataset.paletteChoice });
    });
    $('theme-button').onclick = () => changed({ theme: effective() === 'dark' ? 'light' : 'dark' });
    trigger.onclick = () => {
      if (!panel.hidden) return close();
      panel.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      panel.querySelector('[data-theme-choice][aria-pressed="true"]')?.focus();
    };
    $('theme-close').onclick = () => close(true);
    document.addEventListener('pointerdown', (event) => {
      if (!event.target.closest('.theme-anchor')) close();
    });
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      }
    });
    panel.addEventListener('focusout', () => {
      setTimeout(() => {
        if (!document.activeElement?.closest('.theme-anchor')) close();
      }, 0);
    });
    media.addEventListener('change', (event) => {
      if (nativeSystem) return;
      system = event.matches ? 'dark' : 'light';
      systemChanged();
    });
    return {
      apply,
      effective,
      close,
      receiveSystem(value) {
        if (!['light', 'dark'].includes(value)) return;
        nativeSystem = true;
        system = value;
        systemChanged();
      },
    };
  }
  window.ReaderTheme = { create };
})();
