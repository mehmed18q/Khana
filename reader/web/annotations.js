/* Text anchors survive reflow and locate unchanged paragraphs after edits. */
(() => {
  'use strict';
  const normalize = text => text.replace(/\s+/g, ' ').trim();
  const hash = text => {
    let value = 2166136261;
    for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
    return (value >>> 0).toString(16);
  };
  function textOf(element) {
    if (element.dataset.apiOperation) return element.dataset.apiOperation;
    if (element.matches('.pdf-page')) return `Page ${Number(element.dataset.pdfPage) + 1}`;
    if (element.matches('.diagram-frame')) return normalize(element.querySelector('.diagram-source code')?.textContent || '');
    const clone = element.cloneNode(true);
    clone.querySelectorAll('button,.annotation-badges,.code-toolbar,.annotation-tools').forEach(node => node.remove());
    return normalize(clone.textContent);
  }
  function prepare(article, add, visit) {
    let heading = '';
    const root = ReaderOpenAPI.contentRoot(article);
    const selector = root !== article ? '[data-api-operation]' : 'h1,h2,h3,h4,h5,h6,p,li,pre,.source-line,.pdf-block,.pdf-page,.table-scroll,.diagram-frame,dt,dd,figcaption,summary';
    const blocks = [...root.querySelectorAll(selector)].filter(node =>
      !node.matches('.empty-document,.structured-source') && (node.matches('.source-line') || !node.parentElement.closest('.table-scroll,pre,li,.diagram-frame,dt,dd,figcaption,summary')));
    return blocks.map((element, index) => {
      element.querySelectorAll(':scope > .annotation-tools,:scope > .annotation-badges').forEach(node => node.remove());
      if (/^H[1-6]$/.test(element.tagName)) heading = element.id;
      const text = textOf(element);
      const info = { element, index, tag: element.dataset.apiOperation ? 'api-operation' : element.matches('.diagram-frame') ? 'diagram' : element.matches('.table-scroll') ? 'table' : element.tagName.toLowerCase(),
        text, hash: hash(text), heading };
      element.dataset.readingBlock = index;
      const tools = document.createElement('span'); tools.className = 'annotation-tools'; tools.dir = 'ltr';
      for (const [kind, symbol, title] of [['mark', '▱', 'Add a mark here'], ['note', '+', 'Add a note here']]) {
        const button = document.createElement('button'); button.type = 'button'; button.dataset.symbol = symbol;
        button.title = title; button.setAttribute('aria-label', title);
        button.addEventListener('mousedown', event => event.preventDefault());
        button.onclick = event => { event.stopPropagation(); add(kind, info); };
        tools.append(button);
      }
      const badges = document.createElement('span'); badges.className = 'annotation-badges'; badges.dir = 'ltr';
      badges.onclick = event => {
        const button = event.target.closest('[data-annotation]');
        if (button) { event.stopPropagation(); visit(button.dataset.annotation); }
      };
      element.append(tools, badges);
      return info;
    });
  }
  function capture(blocks, scroller, selected, fingerprint) {
    if (!blocks.length) return null;
    const selection = window.getSelection();
    if (!selected && selection?.rangeCount && !selection.isCollapsed) {
      const node = selection.getRangeAt(0).startContainer;
      const element = (node.nodeType === 1 ? node : node.parentElement).closest('[data-reading-block]');
      selected = blocks.find(block => block.element === element);
    }
    if (!selected) {
      const target = scroller.getBoundingClientRect().top + 40;
      selected = blocks.find(block => block.element.getBoundingClientRect().bottom > target) || blocks.at(-1);
    }
    const { index, text, tag, heading } = selected;
    const rect = selected.element.getBoundingClientRect();
    const top = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    let quote = '', quoteOffset = 0;
    if (selection?.rangeCount && !selection.isCollapsed && selected.element.contains(selection.anchorNode)) {
      const candidate = normalize(selection.toString()).slice(0, 500);
      if (candidate && text.includes(candidate)) { quote = candidate; quoteOffset = text.indexOf(candidate); }
    }
    return { index, tag, text: text.slice(0, 320), tail: text.slice(-100), hash: selected.hash,
      before: blocks[index - 1]?.text.slice(-160) || '', after: blocks[index + 1]?.text.slice(0, 160) || '',
      heading, quote, quoteOffset, fingerprint,
      progress: Math.max(0, Math.min(1, top / Math.max(1, scroller.scrollHeight - scroller.clientHeight))) };
  }
  function locate(blocks, anchor) {
    if (!anchor || !blocks.length) return { block: null, exact: false };
    const exact = blocks.filter(block => block.hash === anchor.hash && block.text.startsWith(anchor.text) && block.text.endsWith(anchor.tail));
    const candidates = exact.length ? exact : blocks.filter(block =>
      (anchor.quote && block.text.includes(anchor.quote)) || (anchor.text.length > 20 && block.text.includes(anchor.text)));
    const score = block => (block.heading === anchor.heading ? 10 : 0) + (block.tag === anchor.tag ? 5 : 0)
      + (anchor.before && blocks[block.index - 1]?.text.endsWith(anchor.before) ? 20 : 0)
      + (anchor.after && blocks[block.index + 1]?.text.startsWith(anchor.after) ? 20 : 0)
      - Math.abs(block.index - anchor.index) / Math.max(1, blocks.length);
    if (candidates.length) return { block: candidates.sort((a, b) => score(b) - score(a))[0], exact: Boolean(exact.length) };
    // An edited/deleted paragraph is never presented as an exact match.
    return { block: blocks[Math.min(anchor.index, blocks.length - 1)], exact: false };
  }
  function decorate(blocks, annotations, resumeId) {
    for (const block of blocks) {
      block.element.classList.remove('has-reading-mark', 'has-reading-note', 'resume-location');
      block.element.querySelector(':scope > .annotation-badges')?.replaceChildren();
    }
    for (const item of annotations) {
      const { block, exact } = locate(blocks, item.anchor);
      if (!block || !exact) continue;
      block.element.classList.add(item.kind === 'note' ? 'has-reading-note' : 'has-reading-mark');
      if (item.id === resumeId) block.element.classList.add('resume-location');
      const button = document.createElement('button'); button.type = 'button';
      button.className = `annotation-badge ${item.kind}`; button.dataset.annotation = item.id;
      button.dataset.label = item.kind === 'note' ? 'Note' : 'Mark';
      button.title = item.label; button.setAttribute('aria-label', `${item.kind === 'note' ? 'Note' : 'Mark'}: ${item.label}`);
      block.element.querySelector(':scope > .annotation-badges')?.append(button);
    }
  }
  const api = { normalize, hash, prepare, capture, locate, decorate };
  if (typeof window !== 'undefined') window.ReaderAnnotations = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
