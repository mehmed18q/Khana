/* UI-only localization. Observers are scoped to chrome, never to document text. */
(() => {
  'use strict';
  const catalog = new Map(Object.entries(window.ReaderPersian));
  const patterns = [...catalog]
    .filter(([key]) => key.includes('{0}'))
    .map(([key, value]) => [
      new RegExp(
        '^' +
          key
            .split(/(\{\d+\})/)
            .map((part) =>
              /^\{\d+\}$/.test(part) ? '(.*?)' : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
            )
            .join('') +
          '$'
      ),
      value,
    ]);
  let language = 'en';
  const records = new WeakMap();
  const roots = new Set();
  const rootSelector =
    '.sidebar,.topbar,.compact-header,.document-toolbar,.reading-toolbar,.memory-toolbar,.preview-toolbar,.paper-topline,.editor-heading,.editor-footer,.format-toolbar,.statusbar,dialog,.picker-menu,#search-panel,#toast,#file-context-menu,#empty-state,#loading,#drop-overlay,#annotations-panel';
  const excluded =
    'script,style,svg,textarea,.document,.source-editor,.source-mirror,.source-search-layer,.spelling-layer,[translate="no"],.file-name,.library-name,.outline-title,.category-name,.annotation-name,.annotation-jump,.annotation-note,.annotation-excerpt,.annotation-quote,.annotation-context,.annotation-body,.search-result bdi,#current-filename,#compact-filename,#annotation-context,#pdf-text-context';
  function text(value) {
    if (language !== 'fa') return value;
    if (catalog.has(value)) return catalog.get(value);
    for (const [pattern, translated] of patterns) {
      const match = pattern.exec(value);
      if (match)
        return translated.replace(/\{(\d+)\}/g, (_, index) => match[Number(index) + 1] || '');
    }
    const shortcut = /^(.*?)( \([^)]*\))$/.exec(value);
    if (shortcut && catalog.has(shortcut[1])) return catalog.get(shortcut[1]) + shortcut[2];
    return value;
  }
  function update(node, key, value, write) {
    let saved = records.get(node);
    if (!saved) {
      saved = {};
      records.set(node, saved);
    }
    const previous = saved[key];
    const original = previous?.output === value ? previous.original : value;
    const trimmed = original.trim().replace(/\s+/g, ' '),
      translated = text(trimmed);
    const output =
      translated === trimmed ? original : original.replace(/\S[\s\S]*\S|\S/, translated);
    saved[key] = { original, output };
    if (output !== value) write(output);
  }
  function translate(root) {
    if (!root?.isConnected) return;
    if (![Node.ELEMENT_NODE, Node.TEXT_NODE].includes(root.nodeType)) return;
    const element = root.nodeType === Node.TEXT_NODE ? root.parentElement : root;
    if (element.closest(excluded)) return;
    if (root.nodeType === Node.TEXT_NODE) {
      update(root, 'text', root.data, (value) => {
        root.data = value;
      });
      return;
    }
    for (const name of ['title', 'aria-label', 'placeholder'])
      if (root.hasAttribute(name))
        update(root, name, root.getAttribute(name), (value) => root.setAttribute(name, value));
    for (const child of root.childNodes) translate(child);
  }
  const observer = new MutationObserver((changes) => {
    if (language !== 'fa') return;
    const pending = new Set();
    for (const change of changes) {
      if (change.type === 'childList') for (const node of change.addedNodes) pending.add(node);
      else pending.add(change.target);
    }
    for (const node of pending)
      if (![...pending].some((parent) => parent !== node && parent.contains(node))) translate(node);
  });
  function register() {
    document.querySelectorAll(rootSelector).forEach((root) => {
      if ([...roots].some((parent) => parent.contains(root))) return;
      roots.add(root);
      observer.observe(root, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['title', 'aria-label', 'placeholder'],
      });
    });
  }
  function apply(value) {
    const next = value === 'fa' ? 'fa' : 'en';
    if (next === language && roots.size) return;
    language = next;
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'fa' ? 'rtl' : 'ltr';
    register();
    for (const root of roots) translate(root);
    document.dispatchEvent(new CustomEvent('reader-language-changed'));
  }
  window.ReaderI18n = {
    apply,
    text,
    get language() {
      return language;
    },
  };
})();
