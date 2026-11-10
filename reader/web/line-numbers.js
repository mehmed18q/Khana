/* Source coordinates shared by the editor gutter, navigation and scroll sync. */
(() => {
  'use strict';
  const mirrorStyles = [
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
  ];
  function gutter(className) {
    const node = document.createElement('div');
    node.className = `line-numbers ${className}`;
    node.setAttribute('aria-hidden', 'true');
    node.dir = 'ltr';
    return node;
  }
  function number(line, top, active = false) {
    const node = document.createElement('span');
    node.dataset.line = line + 1;
    node.textContent = line + 1;
    node.style.top = `${top}px`;
    node.classList.toggle('current-line', active);
    return node;
  }
  function createEditor({ container, current }) {
    const labels = gutter('editor-line-numbers'),
      mirror = document.createElement('div'),
      detail = document.createElement('div');
    for (const node of [mirror, detail]) {
      node.className = 'source-mirror';
      node.setAttribute('aria-hidden', 'true');
      document.body.append(node);
    }
    container.append(labels);
    let key = '',
      source = null,
      lines = [],
      points = [],
      stride = 1,
      frame = 0;
    const chunks = new Map();
    function measure(field) {
      const text = field.value,
        previousLines = lines;
      const changed = source !== text;
      if (changed) {
        source = text;
        lines = ReaderSourceText.get(field).lines;
        const width = `${Math.max(3, String(lines.length).length) * 8 + 18}px`;
        if (container.style.getPropertyValue('--line-gutter-width') !== width)
          container.style.setProperty('--line-gutter-width', width);
      }
      const css = getComputedStyle(field),
        next = [field.clientWidth, field.dir, ...mirrorStyles.map((name) => css[name])].join('\0');
      if (!changed && key === next) return points;
      const reuse = key === next && stride === 1 && lines.length <= 10000;
      key = next;
      chunks.clear();
      if (!reuse)
        for (const node of [mirror, detail]) {
          for (const name of mirrorStyles) node.style[name] = css[name];
          node.dir = field.dir;
          node.style.width = `${field.clientWidth}px`;
        }
      stride = Math.max(1, Math.ceil(lines.length / 10000));
      let first = 0,
        tail = 0;
      if (reuse) {
        while (
          first < Math.min(previousLines.length, lines.length) &&
          previousLines[first] === lines[first]
        )
          first++;
        while (
          tail < Math.min(previousLines.length, lines.length) - first &&
          previousLines.at(-tail - 1) === lines.at(-tail - 1)
        )
          tail++;
      }
      const fragment = document.createDocumentFragment();
      for (let i = first; i < lines.length - tail; i += stride) {
        const row = document.createElement('div'),
          text = lines.slice(i, i + stride).join('\n');
        row.dataset.line = i;
        row.textContent = text + (!text || text.endsWith('\n') ? '\u200b' : '');
        fragment.append(row);
      }
      if (reuse) {
        const children = [...mirror.children],
          anchor = children[previousLines.length - tail] || null;
        for (let i = first; i < previousLines.length - tail; i++) children[i].remove();
        mirror.insertBefore(fragment, anchor);
        if (previousLines.length !== lines.length)
          for (let i = first; i < mirror.children.length; i++) mirror.children[i].dataset.line = i;
        const boundary = lines.length - tail,
          top = anchor ? anchor.offsetTop : mirror.scrollHeight - parseFloat(css.paddingBottom),
          delta = top - points[previousLines.length - tail][1],
          previous = points;
        points = lines.map((_, i) => {
          if (i < first) return previous[i];
          if (i < boundary) return [i, mirror.children[i].offsetTop];
          return [i, previous[i - lines.length + previousLines.length][1] + delta];
        });
        points.push([
          lines.length,
          top + (previous.at(-1)[1] - previous[previousLines.length - tail][1]),
        ]);
        return points;
      } else mirror.replaceChildren(fragment);
      points = [...mirror.children].map((row) => [Number(row.dataset.line), row.offsetTop]);
      points.push([lines.length, mirror.scrollHeight - parseFloat(css.paddingBottom)]);
      return points;
    }
    function chunk(index) {
      if (stride === 1) return [points[index]];
      if (chunks.has(index)) return chunks.get(index);
      const start = points[index][0],
        fragment = document.createDocumentFragment();
      for (const text of lines.slice(start, start + stride)) {
        const row = document.createElement('div');
        row.textContent = text || '\u200b';
        fragment.append(row);
      }
      detail.replaceChildren(fragment);
      const offset = detail.firstElementChild.offsetTop;
      const result = [...detail.children].map((row, i) => [
        start + i,
        points[index][1] + row.offsetTop - offset,
      ]);
      // Only visible chunks need exact per-line measurements in very large files.
      if (chunks.size >= 8) chunks.delete(chunks.keys().next().value);
      chunks.set(index, result);
      return result;
    }
    function lineTop(field, line) {
      measure(field);
      const index = Math.floor(Math.max(0, Math.min(lines.length - 1, line)) / stride);
      return chunk(index).find(([value]) => value === line)?.[1] ?? points[index][1];
    }
    function render() {
      const field = current();
      labels.hidden = !field?.getClientRects().length;
      if (labels.hidden) return;
      measure(field);
      const css = getComputedStyle(field),
        top = field.scrollTop,
        bottom = top + field.clientHeight,
        active = ReaderSourceText.position(ReaderSourceText.get(field), field.selectionStart).line,
        fragment = document.createDocumentFragment();
      labels.style.lineHeight = css.lineHeight;
      for (let i = 0; i < points.length - 1; i++) {
        if (points[i + 1][1] < top) continue;
        if (points[i][1] > bottom) break;
        for (const [line, y] of chunk(i)) {
          if (y + parseFloat(css.lineHeight) < top || y > bottom) continue;
          fragment.append(number(line, y - top, line === active));
        }
      }
      labels.replaceChildren(fragment);
    }
    function refresh() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    }
    new ResizeObserver(refresh).observe(container);
    document.fonts.ready.then(refresh);
    return {
      metrics: measure,
      lineTop,
      refresh,
      bind(field) {
        for (const name of ['scroll', 'input', 'select', 'keyup', 'click'])
          field.addEventListener(name, refresh);
      },
    };
  }
  function createReading({ article, scroller }) {
    const frame = document.createElement('div'),
      labels = gutter('reading-line-numbers');
    frame.className = 'reading-frame';
    scroller.before(frame);
    frame.append(scroller, labels);
    let request = 0,
      root = null,
      anchors = [],
      dirty = true,
      disposed = false;
    const visibleAnchors = new Set();
    const visibility = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visibleAnchors.add(entry.target);
          else visibleAnchors.delete(entry.target);
        }
        refresh();
      },
      { root: scroller, rootMargin: '80px 0px' }
    );
    const selector =
      'p,h1,h2,h3,h4,h5,h6,li,pre,table,tr,blockquote,div,section,article,figure,summary,dt,dd,.source-line';
    function sourceRows(node, line, viewport, rows) {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      let text,
        beginning = true;
      while ((text = walker.nextNode())) {
        if (text.parentElement.closest('.annotation-tools,.annotation-badges')) continue;
        let offset = 0;
        while (offset < text.length) {
          if (beginning) {
            const range = new Range();
            range.setStart(text, offset);
            range.setEnd(text, offset + 1);
            const rect = range.getBoundingClientRect();
            if (rect.height && rect.top >= viewport.top - 16 && rect.top < viewport.bottom)
              rows.push({ line, y: rect.top - viewport.top });
          }
          const newline = text.data.indexOf('\n', offset);
          beginning = newline >= 0;
          if (!beginning) break;
          line++;
          offset = newline + 1;
        }
      }
    }
    function render() {
      if (disposed) return;
      const content = ReaderOpenAPI.contentRoot(article);
      if (content !== root) {
        root = content;
        shadow.disconnect();
        if (root !== article)
          shadow.observe(root, { subtree: true, childList: true, attributes: true });
        dirty = true;
      }
      if (dirty) {
        anchors = [...root.querySelectorAll('[data-source-line]')].filter(
          (node) => node.matches(selector) && !node.closest('.diagram-source')
        );
        dirty = false;
        visibility.disconnect();
        visibleAnchors.clear();
        anchors.forEach((node) => visibility.observe(node));
      }
      const visible =
        !article.hidden && !article.classList.contains('pdf-document') && anchors.length > 0;
      labels.hidden = !visible;
      frame.classList.toggle('has-line-numbers', visible);
      if (!visible) return;
      const viewport = scroller.getBoundingClientRect(),
        rows = [],
        seen = new Set(),
        fragment = document.createDocumentFragment();
      for (const node of visibleAnchors) {
        const rect = node.getBoundingClientRect(),
          line = Number(node.dataset.sourceLine);
        if (node.matches('.source-line') && Number(node.dataset.sourceEnd) > line + 1) {
          if (rect.bottom >= viewport.top && rect.top < viewport.bottom)
            sourceRows(node, line, viewport, rows);
          continue;
        }
        if (
          !rect.height ||
          rect.top < viewport.top - 16 ||
          rect.top >= viewport.bottom ||
          !Number.isInteger(line)
        )
          continue;
        rows.push({ line, y: rect.top - viewport.top });
      }
      rows.sort((a, b) => a.y - b.y || a.line - b.line);
      let previous = -Infinity;
      for (const { line, y } of rows) {
        if (seen.has(line) || y - previous < 14) continue;
        fragment.append(number(line, y));
        previous = y;
        seen.add(line);
      }
      labels.replaceChildren(fragment);
    }
    function refresh() {
      cancelAnimationFrame(request);
      request = requestAnimationFrame(render);
    }
    const changed = () => {
        dirty = true;
        refresh();
      },
      observer = new MutationObserver(changed),
      shadow = new MutationObserver(changed),
      size = new ResizeObserver(refresh);
    observer.observe(article, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['data-source-line', 'data-source-end', 'hidden', 'open'],
    });
    size.observe(article);
    size.observe(scroller);
    scroller.addEventListener('scroll', refresh, { passive: true });
    article.addEventListener('toggle', refresh, true);
    document.fonts.ready.then(refresh);
    refresh();
    return {
      refresh,
      dispose() {
        disposed = true;
        cancelAnimationFrame(request);
        observer.disconnect();
        shadow.disconnect();
        size.disconnect();
        visibility.disconnect();
        scroller.removeEventListener('scroll', refresh);
        article.removeEventListener('toggle', refresh, true);
      },
    };
  }
  window.ReaderLineNumbers = { createEditor, createReading };
})();
