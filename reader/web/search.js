/* Literal Unicode search shared by source editing and rendered documents. */
(() => {
  'use strict';
  const word = '[\\p{L}\\p{M}\\p{N}\\p{Pc}\\u200c\\u200d]',
    beforeWord = new RegExp(`${word}$`, 'u'),
    afterWord = new RegExp(`^${word}`, 'u');

  function matches(text, query, { matchCase = false, wholeWord = false } = {}) {
    if (!query) return [];
    // Folding an entire string can change its length (e.g. İ), corrupting offsets.
    // An escaped Unicode regexp keeps original UTF-16 coordinates and literal text.
    const expression = new RegExp(
        query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
        matchCase ? 'gu' : 'giu'
      ),
      found = [];
    for (const match of text.matchAll(expression)) {
      const start = match.index,
        end = start + match[0].length;
      if (
        wholeWord &&
        (beforeWord.test(text.slice(Math.max(0, start - 2), start)) ||
          afterWord.test(text.slice(end, end + 2)))
      )
        continue;
      found.push({ start, end });
    }
    return found;
  }

  function replacement(text, found, value) {
    if (!found.length) return null;
    const start = found[0].start,
      end = found.at(-1).end,
      parts = [];
    let cursor = start;
    for (const match of found) {
      parts.push(text.slice(cursor, match.start), value);
      cursor = match.end;
    }
    return {
      start,
      end,
      text: parts.join(''),
      selectionStart: start,
      selectionEnd: start + value.length,
    };
  }

  const $ = (id) => document.getElementById(id);
  function create({
    article,
    scroller,
    contentRoot,
    current,
    editor,
    applyEdit,
    edit,
    lineNumbers,
    formatNumber,
  }) {
    const panel = $('search-panel'),
      input = $('search-input'),
      list = $('search-results'),
      resultsDialog = $('search-results-dialog'),
      layer = document.createElement('div'),
      mirror = document.createElement('div');
    layer.className = 'source-search-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.hidden = true;
    mirror.className = 'source-search-text';
    layer.append(mirror);
    $('editor-container').prepend(layer);
    let results = [],
      resultIndex = -1,
      snapshot = null,
      searchTimer = 0,
      resultsFocus = null,
      listed = 0,
      sourceField = null,
      replacementMessage = '',
      replacing = false;

    function highlight(name, ranges) {
      if (!globalThis.CSS?.highlights || typeof Highlight === 'undefined') return;
      const value = new Highlight();
      for (const range of ranges) value.add(range);
      CSS.highlights.set(name, value);
    }
    function removeHighlights() {
      for (const name of [
        'reader-search',
        'reader-current',
        'reader-source-search',
        'reader-source-current',
      ])
        globalThis.CSS?.highlights?.delete(name);
      sourceField?.classList.remove('searching-source');
      sourceField = null;
      layer.hidden = true;
    }
    function clear() {
      clearTimeout(searchTimer);
      removeHighlights();
      results = [];
      resultIndex = -1;
      snapshot = null;
      list.replaceChildren();
      updateControls();
    }
    function clearPreview() {
      globalThis.CSS?.highlights?.delete('reader-search');
      globalThis.CSS?.highlights?.delete('reader-current');
      if (!snapshot?.field) snapshot = null;
    }

    function renderedText() {
      const root = contentRoot(),
        nodes = [],
        walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
          acceptNode(node) {
            const closed = node.parentElement?.closest('details:not([open])');
            if (closed && !closed.querySelector(':scope > summary')?.contains(node))
              return NodeFilter.FILTER_REJECT;
            if (node.nodeType === Node.ELEMENT_NODE) {
              if (
                node.matches(
                  'input,textarea,select,style,script,[hidden],.katex-mathml,.code-toolbar,.annotation-tools,.annotation-badges,.empty-document'
                ) ||
                (node.getAttribute('aria-hidden') === 'true' && !node.matches('.katex-html')) ||
                (node.matches('button') &&
                  !node.matches('.opblock-summary-control,.model-box-control'))
              )
                return NodeFilter.FILTER_REJECT;
              const css = getComputedStyle(node);
              if (css.display === 'none' || css.visibility === 'hidden')
                return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
          },
        });
      let full = '',
        previousBlock = null,
        node;
      while ((node = walker.nextNode())) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.tagName === 'BR') full += '\n';
          continue;
        }
        const block = node.parentElement?.closest(
          'p,h1,h2,h3,h4,h5,h6,li,td,th,pre,div,section,article,blockquote,dt,dd,tr,figcaption,.source-line'
        );
        if (full && block !== previousBlock && !full.endsWith('\n')) full += '\n';
        previousBlock = block;
        // Match the whitespace the reader sees, retaining original DOM offsets
        // for ranges across inline formatting and collapsed HTML whitespace.
        const collapse = ['normal', 'nowrap'].includes(
            getComputedStyle(node.parentElement || root.host || article).whiteSpace
          ),
          offsets = [];
        let text = '';
        for (let i = 0; i < node.length; i++) {
          const char = node.data[i];
          if (collapse && /[\t\n\r\f ]/.test(char)) {
            const start = i;
            while (i + 1 < node.length && /[\t\n\r\f ]/.test(node.data[i + 1])) i++;
            if (!text && (!full || /[ \n]$/.test(full))) continue;
            offsets.push(start);
            text += ' ';
          } else {
            offsets.push(i);
            text += char === '\u00a0' ? ' ' : char;
          }
        }
        offsets.push(node.length);
        if (!text) continue;
        nodes.push({
          node,
          original: node.data,
          offsets,
          start: full.length,
          end: full.length + text.length,
        });
        full += text;
      }
      return { text: full, nodes, root };
    }

    function syncMirror() {
      const field = sourceField;
      if (!field || layer.hidden) return;
      lineNumbers.metrics(field);
      const css = getComputedStyle(field);
      for (const name of [
        'font',
        'lineHeight',
        'letterSpacing',
        'padding',
        'tabSize',
        'whiteSpace',
        'overflowWrap',
        'wordBreak',
        'textAlign',
        'unicodeBidi',
      ])
        mirror.style[name] = css[name];
      mirror.dir = field.dir;
      mirror.style.width = `${field.clientWidth}px`;
      layer.style.left = `${field.offsetLeft}px`;
      layer.style.top = `${field.offsetTop}px`;
      layer.style.width = `${field.clientWidth}px`;
      layer.style.height = `${field.clientHeight}px`;
      mirror.style.transform = `translate(${-field.scrollLeft}px, ${-field.scrollTop}px)`;
    }

    function buildRanges(data) {
      if (data.field) {
        sourceField = data.field;
        mirror.textContent = data.text + '\u200b';
        layer.hidden = false;
        sourceField.classList.add('searching-source');
        syncMirror();
        for (const match of results) {
          const range = new Range();
          range.setStart(mirror.firstChild, match.start);
          range.setEnd(mirror.firstChild, match.end);
          match.range = range;
        }
      } else {
        let first = 0,
          last = 0;
        for (const match of results) {
          while (data.nodes[first]?.end <= match.start) first++;
          last = Math.max(first, last);
          while (data.nodes[last]?.end < match.end) last++;
          const a = data.nodes[first],
            b = data.nodes[last];
          if (!a || !b || match.start < a.start || match.end > b.end) continue;
          const range = new Range();
          range.setStart(a.node, a.offsets[match.start - a.start]);
          range.setEnd(b.node, b.offsets[match.end - b.start]);
          match.range = range;
        }
        results = results.filter((match) => match.range);
      }
      highlight(
        data.field ? 'reader-source-search' : 'reader-search',
        results.map((match) => match.range)
      );
    }

    function updateControls() {
      const doc = current(),
        field = editor(),
        writable = Boolean(doc && !doc.moving && field && !field.readOnly);
      $('search-scope').textContent = doc
        ? field
          ? 'Searching source text'
          : 'Searching document'
        : 'No document';
      $('search-count').textContent = input.value
        ? results.length
          ? `${formatNumber(resultIndex + 1)} of ${formatNumber(results.length)}`
          : 'No matches'
        : '';
      for (const id of ['search-next', 'search-prev', 'search-all'])
        $(id).disabled = !doc || !input.value;
      $('search-replace').disabled = $('search-replace-all').disabled =
        !writable || !results.length;
      $('replace-input').disabled = !writable;
      if (!writable)
        $('replace-status').textContent =
          doc?.format === 'PDF'
            ? 'Use Edit text on the PDF page to replace text.'
            : doc?.moving
              ? 'This document is being moved.'
              : 'Switch to Edit & Preview to replace source text.';
      else $('replace-status').textContent = replacementMessage;
    }

    function renderList(reset = true) {
      if (!resultsDialog.open) return;
      $('search-results-summary').textContent =
        `${formatNumber(results.length)} ${results.length === 1 ? 'match' : 'matches'} for “${input.value}” · ${current()?.name || ''}`;
      if (reset) {
        list.replaceChildren();
        listed = 0;
        list.scrollTop = 0;
      }
      list.querySelector('.search-more')?.remove();
      const fragment = document.createDocumentFragment(),
        limit = Math.min(results.length, listed + 100),
        text = snapshot.text;
      for (; listed < limit; listed++) {
        const index = listed,
          match = results[index],
          button = document.createElement('button'),
          location = document.createElement('span'),
          context = document.createElement('bdi'),
          mark = document.createElement('mark');
        button.className = 'search-result';
        button.dataset.index = index;
        button.setAttribute('aria-current', String(index === resultIndex));
        location.className = 'search-result-location';
        if (snapshot.field) {
          const prefix = text.slice(0, match.start).split('\n');
          location.textContent = `Ln ${formatNumber(prefix.length)}, Col ${formatNumber([...prefix.at(-1)].length + 1)}`;
        } else location.textContent = `Match ${formatNumber(index + 1)}`;
        mark.textContent = text.slice(match.start, match.end);
        context.append(
          text.slice(Math.max(0, match.start - 45), match.start).replace(/\s+/g, ' '),
          mark,
          text.slice(match.end, match.end + 65).replace(/\s+/g, ' ')
        );
        button.append(location, context);
        button.onclick = () => {
          // An edit or tab switch may invalidate an old result before its click.
          const previous = snapshot;
          search({ navigate: false });
          if (snapshot !== previous) {
            list.querySelector('.search-result')?.focus();
            return;
          }
          resultIndex = index;
          const target = editor() || article;
          resultsFocus = target;
          resultsDialog.close();
          selectResult(true);
          target.focus({ preventScroll: true });
        };
        fragment.append(button);
      }
      list.append(fragment);
      if (listed < results.length) {
        const more = document.createElement('button');
        more.className = 'secondary-button search-more';
        more.textContent = `Show more (${formatNumber(results.length - listed)} remaining)`;
        more.onclick = () => renderList(false);
        list.append(more);
      }
      if (!results.length) list.textContent = input.value ? 'No matches' : 'Enter text to find.';
    }

    function openResults() {
      search({ navigate: false });
      if (!snapshot) return;
      resultsFocus = document.activeElement;
      resultsDialog.showModal();
      renderList();
      (
        list.querySelector('[aria-current="true"]') ||
        list.querySelector('.search-result') ||
        $('search-results-close')
      ).focus();
    }

    function selectResult(navigate = true) {
      updateControls();
      const match = results[resultIndex];
      if (!match) return;
      highlight(snapshot.field ? 'reader-source-current' : 'reader-current', [match.range]);
      for (const button of list.querySelectorAll('[data-index]'))
        button.setAttribute('aria-current', String(Number(button.dataset.index) === resultIndex));
      if (!navigate) return;
      if (snapshot.field) {
        const field = snapshot.field;
        field.setSelectionRange(match.start, match.end);
        syncMirror();
        const rect = match.range.getBoundingClientRect(),
          viewport = field.getBoundingClientRect();
        field.scrollTop += rect.top - viewport.top - viewport.height / 3;
        syncMirror();
      } else {
        const rect = match.range.getBoundingClientRect(),
          viewport = scroller.getBoundingClientRect();
        scroller.scrollBy({
          top: rect.top - viewport.top - viewport.height / 3,
          behavior: 'instant',
        });
      }
    }

    function search({ navigate = true, anchor } = {}) {
      clearTimeout(searchTimer);
      if (panel.hidden) return false;
      const doc = current(),
        field = editor() || null;
      if (!doc) {
        clear();
        return true;
      }
      const data = field ? { text: field.value, field } : { ...renderedText(), field };
      data.id = doc.id;
      data.query = input.value;
      data.matchCase = $('search-case').getAttribute('aria-pressed') === 'true';
      data.wholeWord = $('search-word').getAttribute('aria-pressed') === 'true';
      const sameTarget =
          snapshot &&
          snapshot.id === data.id &&
          snapshot.field === field &&
          snapshot.root === data.root,
        sameQuery =
          sameTarget &&
          snapshot.query === data.query &&
          snapshot.matchCase === data.matchCase &&
          snapshot.wholeWord === data.wholeWord,
        unchanged =
          sameQuery &&
          snapshot.text === data.text &&
          (field ||
            snapshot.nodes.every(
              (entry, index) =>
                entry.node === data.nodes[index]?.node &&
                entry.original === data.nodes[index]?.original
            ));
      if (unchanged && anchor === undefined) {
        syncMirror();
        selectResult(navigate);
        return false;
      }
      const offset =
        anchor ?? (sameQuery ? results[resultIndex]?.start : field?.selectionStart) ?? 0;
      if (!replacing) replacementMessage = '';
      removeHighlights();
      results = matches(data.text, data.query, data);
      snapshot = data;
      buildRanges(data);
      resultIndex = results.findIndex((match) => match.start >= offset);
      if (resultIndex < 0) resultIndex = results.length ? 0 : -1;
      renderList();
      selectResult(navigate);
      return true;
    }

    function next(delta = 1) {
      if (panel.hidden) {
        openSearch();
        return;
      }
      const refreshed = search({ navigate: false });
      if (results.length && !refreshed)
        resultIndex = (resultIndex + delta + results.length) % results.length;
      else if (results.length && delta < 0)
        resultIndex = (resultIndex - 1 + results.length) % results.length;
      selectResult();
    }
    function replace(allMatches = false) {
      search({ navigate: false });
      const field = editor(),
        doc = current();
      if (!field || field.readOnly || doc?.moving || !results.length || snapshot.field !== field)
        return;
      const found = allMatches ? results : [results[resultIndex]],
        value = $('replace-input').value,
        operation = replacement(field.value, found, value),
        count = found.length,
        focus = document.activeElement;
      replacing = true;
      try {
        if (!applyEdit(field, operation)) return;
        search({ anchor: allMatches ? operation.start : operation.start + value.length });
        replacementMessage = `${formatNumber(count)} ${count === 1 ? 'match' : 'matches'} replaced. Ctrl+Z to undo.`;
        updateControls();
      } finally {
        replacing = false;
        if (focus?.isConnected) focus.focus({ preventScroll: true });
      }
    }

    function showReplace(enabled) {
      $('replace-controls').hidden = !enabled;
      const toggle = $('search-toggle-replace');
      toggle.setAttribute('aria-expanded', String(enabled));
      toggle.setAttribute('aria-label', enabled ? 'Hide Replace' : 'Show Replace');
      toggle.title = enabled ? 'Hide Replace' : 'Show Replace (Ctrl+H)';
      if (enabled && current() && current().format !== 'PDF' && !current().moving) edit();
    }

    function openSearch(replaceMode = false) {
      if (document.querySelector('dialog[open]')) return;
      const field = editor();
      const selection =
        field && document.activeElement === field
          ? field.value.slice(field.selectionStart, field.selectionEnd)
          : document.getSelection()?.toString();
      if (selection && !selection.includes('\n')) input.value = selection;
      showReplace(replaceMode);
      panel.hidden = false;
      search();
      const target = replaceMode && !$('replace-input').disabled ? $('replace-input') : input;
      target.focus();
      target.select();
    }
    function closeSearch() {
      if (resultsDialog.open) resultsDialog.close();
      panel.hidden = true;
      showReplace(false);
      clear();
      (editor() || article).focus({ preventScroll: true });
    }
    function changed(kind) {
      if (panel.hidden || replacing) return;
      if (kind === 'view') {
        search({ navigate: false });
        return;
      }
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => search({ navigate: false }), 80);
    }
    $('search-button').onclick = () => openSearch();
    $('search-close').onclick = closeSearch;
    $('search-toggle-replace').onclick = () => {
      const enabled = $('replace-controls').hidden;
      showReplace(enabled);
      search({ navigate: false });
      (enabled && !$('replace-input').disabled ? $('replace-input') : input).focus();
    };
    input.oninput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => search(), 100);
    };
    input.onkeydown = (event) => {
      if (event.key !== 'Enter' || event.isComposing) return;
      event.preventDefault();
      next(event.shiftKey ? -1 : 1);
    };
    $('replace-input').onkeydown = (event) => {
      if (event.key !== 'Enter' || event.isComposing) return;
      event.preventDefault();
      replace(event.ctrlKey || event.metaKey);
    };
    for (const id of ['search-case', 'search-word']) {
      const button = $(id);
      button.onmousedown = (event) => event.preventDefault();
      button.onclick = () => {
        button.setAttribute('aria-pressed', String(button.getAttribute('aria-pressed') !== 'true'));
        search();
      };
    }
    $('search-prev').onclick = () => next(-1);
    $('search-next').onclick = () => next();
    $('search-all').onclick = openResults;
    $('search-results-close').onclick = () => resultsDialog.close();
    resultsDialog.addEventListener('close', () => {
      if (resultsDialog.open) return;
      if (resultsFocus?.isConnected) resultsFocus.focus({ preventScroll: true });
      resultsFocus = null;
      list.replaceChildren();
    });
    $('search-replace').onclick = () => replace();
    $('search-replace-all').onclick = () => replace(true);
    $('editor-container').addEventListener('scroll', syncMirror, true);
    new ResizeObserver(syncMirror).observe($('editor-container'));
    document.fonts.ready.then(syncMirror);
    return { search, clear, clearPreview, open: openSearch, close: closeSearch, next, changed };
  }
  if (typeof window !== 'undefined') window.ReaderSearch = { create };
  if (typeof module !== 'undefined') module.exports = { matches, replacement };
})();
