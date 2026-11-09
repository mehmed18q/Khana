/* Direction is presentation metadata. Source text is never changed. */
(() => {
  'use strict';
  const BLOCKS = 'p,h1,h2,h3,h4,h5,h6,li,th,td';
  const isRtl = (char) =>
    /[\p{Script=Arabic}\p{Script=Hebrew}]/u.test(char) && /\p{Letter}/u.test(char);
  const isLatin = (char) => /\p{Script=Latin}/u.test(char) && /\p{Letter}/u.test(char);

  function firstDirection(text, fallback = 'rtl') {
    for (const char of text) {
      if (isRtl(char)) return 'rtl';
      if (/\p{Letter}/u.test(char)) return 'ltr';
    }
    return fallback;
  }

  function detectDirection(text, fallback = 'rtl') {
    const prose = text.replace(/(?:https?:\/\/|www\.)\S+/g, '');
    const rtl = [...prose].filter(isRtl).length;
    const latin = [...prose].filter(isLatin).length;
    if (!rtl && !latin) return firstDirection(prose, fallback);
    if (!rtl) return 'ltr';
    if (!latin) return 'rtl';
    // A Persian sentence often starts with a product name. Prefer its prose
    // language when enough Persian letters follow that leading Latin phrase.
    if (firstDirection(prose) === 'rtl' || rtl >= latin * 0.6) return 'rtl';
    return 'ltr';
  }

  function ownProse(element) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let text = '',
      node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (parent.closest('code,pre,button,svg,.math-expression')) continue;
      if (parent.closest(BLOCKS) !== element) continue;
      text += node.textContent;
    }
    return text;
  }

  function isolateLatin(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) {
      if (
        !node.parentElement.closest('pre,code,bdi,button,svg,.math-expression') &&
        /[A-Za-z0-9]/.test(node.textContent)
      )
        nodes.push(node);
    }
    const runs =
      /(?:https?:\/\/[^\s<>"«»]+|[A-Za-z0-9][A-Za-z0-9_]*(?:[./@:+#-][A-Za-z0-9_]+)*(?:[ \t]+[A-Za-z0-9][A-Za-z0-9_]*(?:[./@:+#-][A-Za-z0-9_]+)*)*)/g;
    for (const node of nodes) {
      const fragment = document.createDocumentFragment();
      let offset = 0;
      for (const match of node.textContent.matchAll(runs)) {
        fragment.append(node.textContent.slice(offset, match.index));
        const isolated = document.createElement('bdi');
        isolated.dir = 'ltr';
        isolated.textContent = match[0];
        fragment.append(isolated);
        offset = match.index + match[0].length;
      }
      fragment.append(node.textContent.slice(offset));
      node.replaceWith(fragment);
    }
  }

  function prepare(root) {
    root.querySelectorAll(BLOCKS).forEach((element, index) => {
      element.dataset.block = String(index);
      const explicit = element.closest('[dir]');
      element.dataset.detected =
        explicit &&
        explicit !== root &&
        root.contains(explicit) &&
        ['rtl', 'ltr'].includes(explicit.dir)
          ? explicit.dir
          : detectDirection(ownProse(element));
    });
    root.querySelectorAll('pre').forEach((element) => {
      element.dir = 'ltr';
    });
    root.querySelectorAll('code').forEach((element) => {
      element.dir = element.closest('pre') ? 'ltr' : firstDirection(element.textContent, 'ltr');
    });
    root.querySelectorAll('a').forEach((element) => {
      element.dir = firstDirection(element.textContent);
    });
    isolateLatin(root);
    // Keep an English phrase together even across **bold**, links, or inline
    // code; independent isolates alone would reverse those pieces in RTL prose.
    root.querySelectorAll(`${BLOCKS},strong,em,s`).forEach((element) => {
      if (element.closest('.math-expression')) return;
      let group = [],
        meaningful = 0;
      const flush = () => {
        while (group.length && group.at(-1).nodeType === 3) group.pop();
        if (meaningful > 1) {
          const wrapper = document.createElement('bdi');
          wrapper.dir = 'ltr';
          group[0].before(wrapper);
          group.forEach((node) => wrapper.append(node));
        }
        group = [];
        meaningful = 0;
      };
      for (const node of [...element.childNodes]) {
        if (node.nodeType === 3 && /^\s+$/.test(node.textContent) && group.length) {
          group.push(node);
          continue;
        }
        const inline = node.nodeType === 1 && /^(BDI|STRONG|EM|S|A|CODE|SPAN)$/.test(node.tagName);
        const ltr =
          inline &&
          !node.classList.contains('math-expression') &&
          (node.dir === 'ltr' ||
            (![...node.textContent].some(isRtl) && /[A-Za-z0-9]/.test(node.textContent)));
        if (ltr) {
          group.push(node);
          meaningful++;
        } else flush();
      }
      flush();
    });
  }

  function apply(root, mode = 'smart', overrides = {}) {
    root.querySelectorAll('[data-block]').forEach((element) => {
      element.dir =
        overrides[element.dataset.block] || (mode === 'smart' ? element.dataset.detected : mode);
      element
        .querySelector(':scope > .block-direction')
        ?.classList.toggle('manual', Boolean(overrides[element.dataset.block]));
    });
    root.querySelectorAll('ul,ol,blockquote,table').forEach((element) => {
      const child = element.querySelector('[data-block]');
      element.dir = mode === 'smart' ? child?.dir || 'rtl' : mode;
    });
  }

  const api = { detectDirection, firstDirection, prepare, apply };
  if (typeof module !== 'undefined') module.exports = api;
  if (typeof window !== 'undefined') window.ReaderBidi = api;
})();
