/* Search ranges and panel state are local to the active document view. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ article, scroller, contentRoot, current, formatNumber }) {
    let results = [],
      resultIndex = -1,
      searchTimer;
    function clearHighlights() {
      results = [];
      resultIndex = -1;
      CSS.highlights?.delete('reader-search');
      CSS.highlights?.delete('reader-current');
      $('search-count').textContent = '';
    }

    function search() {
      clearTimeout(searchTimer);
      clearHighlights();
      const query = $('search-input').value.toLocaleLowerCase();
      if (!query || !current()) return;
      // Search across inline markup, but keep separate paragraphs separated.
      const walker = document.createTreeWalker(contentRoot(), NodeFilter.SHOW_TEXT);
      const nodes = [];
      let node,
        full = '',
        previousBlock = null;
      while ((node = walker.nextNode())) {
        if (node.parentElement.closest('button,.code-toolbar,style,script')) continue;
        const block = node.parentElement.closest('p,h1,h2,h3,h4,h5,h6,li,td,th,pre');
        if (previousBlock && block !== previousBlock) full += '\n';
        previousBlock = block;
        nodes.push({ node, start: full.length, end: full.length + node.textContent.length });
        full += node.textContent;
      }
      const lowered = full.toLocaleLowerCase();
      let start = 0;
      while ((start = lowered.indexOf(query, start)) >= 0 && results.length < 2000) {
        const end = start + query.length;
        const first = nodes.find((item) => item.end > start && item.start <= start);
        const last = nodes.find((item) => item.start < end && item.end >= end);
        if (first && last) {
          const range = new Range();
          range.setStart(first.node, start - first.start);
          range.setEnd(last.node, end - last.start);
          results.push(range);
        }
        start = end;
      }
      if (CSS.highlights && results.length)
        CSS.highlights.set('reader-search', new Highlight(...results));
      resultIndex = results.length ? 0 : -1;
      selectResult(0);
    }

    function selectResult(delta) {
      if (results.length) {
        resultIndex = (resultIndex + delta + results.length) % results.length;
        const selected = results[resultIndex];
        CSS.highlights?.set('reader-current', new Highlight(selected));
        const rect = selected.getBoundingClientRect(),
          viewport = scroller.getBoundingClientRect();
        scroller.scrollBy({
          top: rect.top - viewport.top - viewport.height / 3,
          behavior: 'instant',
        });
        $('search-count').textContent =
          `${formatNumber(resultIndex + 1)} of ${formatNumber(results.length)}${results.length === 2000 ? '+' : ''}`;
      } else $('search-count').textContent = $('search-input').value ? 'No matches' : '';
    }

    function openSearch() {
      $('search-panel').hidden = false;
      $('search-input').focus();
      $('search-input').select();
      if ($('search-input').value) search();
    }
    function closeSearch() {
      clearTimeout(searchTimer);
      $('search-panel').hidden = true;
      clearHighlights();
      article.focus({ preventScroll: true });
    }
    $('search-button').onclick = openSearch;
    $('search-close').onclick = closeSearch;
    $('search-input').oninput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(search, 140);
    };
    $('search-input').onkeydown = (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        selectResult(event.shiftKey ? -1 : 1);
      }
    };
    $('search-prev').onclick = () => selectResult(-1);
    $('search-next').onclick = () => selectResult(1);

    return { search, clear: clearHighlights, open: openSearch, close: closeSearch };
  }
  window.ReaderSearch = { create };
})();
