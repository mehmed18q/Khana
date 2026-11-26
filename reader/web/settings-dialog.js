/* The Settings sheet and the close prompt, shared in look and behavior with Bandar.
   Theme and palette buttons carry data-theme-choice / data-palette-choice, so the
   theme module binds and highlights them; other controls name a setting key. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const CLOSE_CHOICES = new Set(['background', 'quit']);

  function create({ settings, change, native, unsaved, formatNumber }) {
    const sheet = $('settings-dialog'),
      prompt = $('close-dialog');

    function render() {
      const values = settings();
      sheet.querySelectorAll('button[data-setting][data-value]').forEach((button) => {
        button.setAttribute(
          'aria-pressed',
          String(values[button.dataset.setting] === button.dataset.value)
        );
      });
      sheet.querySelectorAll('input[type="checkbox"][data-setting]').forEach((input) => {
        input.checked = Boolean(values[input.dataset.setting]);
      });
    }

    function open() {
      if (sheet.open) return;
      render();
      sheet.showModal();
      sheet.querySelector('.sheet-head .icon-button').focus();
    }

    sheet.addEventListener('click', (event) => {
      const choice = event.target.closest('button[data-setting][data-value]');
      if (choice) change({ [choice.dataset.setting]: choice.dataset.value });
    });
    sheet.addEventListener('change', (event) => {
      const key = event.target.dataset.setting;
      if (key && event.target.type === 'checkbox') change({ [key]: event.target.checked });
    });
    $('settings-logs').onclick = () => native()?.openLogs();
    $('settings-github').onclick = () => $('repository-link').click();
    $('settings-button').onclick = open;

    /* The window's close button on the last visible window: run in the background
       or quit. A remembered answer becomes the "When the last window is closed" setting. */
    function askClose({ tray }) {
      if (prompt.open) return;
      const count = unsaved();
      $('close-message').textContent = count
        ? `Unsaved documents: ${formatNumber(count)}. In the background they stay open; quitting asks you to save them.`
        : 'Keep Khana running in the background, or quit?';
      $('close-hint').textContent = tray
        ? 'In the background, click the tray icon to show the window again.'
        : 'In the background, open Khana again from the applications menu to show the window.';
      $('close-remember').checked = false;
      prompt.returnValue = '';
      prompt.showModal();
      $('close-background').focus();
    }

    prompt.addEventListener('close', () => {
      const choice = prompt.returnValue;
      if (!CLOSE_CHOICES.has(choice)) return;
      if ($('close-remember').checked) change({ closeAction: choice });
      native()?.closeChoice(choice);
    });

    return {
      open,
      render,
      askClose,
      get isOpen() {
        return sheet.open;
      },
    };
  }

  window.ReaderSettingsDialog = { create };
})();
