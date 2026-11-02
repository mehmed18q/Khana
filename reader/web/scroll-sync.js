/* Bidirectional source/preview scroll mapping, including wrapped source lines. */
(() => {
  'use strict';
  function interpolate(points, value, axis = 0) {
    if (!points.length) return 0;
    const other = 1 - axis;
    if (value <= points[0][axis]) return points[0][other];
    for (let i = 1; i < points.length; i++) {
      if (value <= points[i][axis]) {
        const a = points[i - 1],
          b = points[i],
          width = b[axis] - a[axis];
        return width > 0
          ? a[other] + ((b[other] - a[other]) * (value - a[axis])) / width
          : b[other];
      }
    }
    return points.at(-1)[other];
  }
  function create({ article, scroller, editor, current, enabled }) {
    const mirror = document.createElement('div');
    mirror.setAttribute('aria-hidden', 'true');
    mirror.className = 'source-mirror';
    document.body.append(mirror);
    let points = [],
      metrics = [],
      cacheKey = '',
      frame = 0,
      paused = false,
      driver = 'preview';
    const expected = new WeakMap();
    const active = () =>
      enabled() &&
      current()?.editMode &&
      current()?.format !== 'PDF' &&
      editor() &&
      !current().previewPending &&
      !current().apiRendering;
    function sourceMetrics() {
      const field = editor(),
        css = getComputedStyle(field);
      const key = [field.value, field.clientWidth, css.font, css.padding, field.dir].join('\0');
      if (key === cacheKey) return;
      cacheKey = key;
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
      mirror.replaceChildren();
      const lines = field.value.split('\n'),
        stride = Math.max(1, Math.ceil(lines.length / 10000));
      const fragment = document.createDocumentFragment();
      for (let i = 0; i < lines.length; i += stride) {
        const span = document.createElement('div');
        span.dataset.line = i;
        span.textContent = lines.slice(i, i + stride).join('\n') || '\u200b';
        fragment.append(span);
      }
      mirror.append(fragment);
      metrics = [...mirror.children].map((span) => [Number(span.dataset.line), span.offsetTop]);
      metrics.push([lines.length, mirror.scrollHeight - parseFloat(css.paddingBottom)]);
    }
    function rebuild() {
      if (!active()) return;
      sourceMetrics();
      const top = scroller.getBoundingClientRect().top,
        candidates = [];
      ReaderOpenAPI.contentRoot(article)
        .querySelectorAll('[data-source-line]')
        .forEach((node) => {
          if (!node.getClientRects().length || node.closest('.diagram-source')) return;
          // Inline HTML tags share the containing block's line and are not scroll anchors.
          if (
            !node.matches(
              'p,h1,h2,h3,h4,h5,h6,li,pre,table,tr,blockquote,div,section,article,figure,summary,dt,dd,.source-line'
            )
          )
            return;
          const rect = node.getBoundingClientRect(),
            line = Number(node.dataset.sourceLine);
          candidates.push({ line, y: rect.top - top + scroller.scrollTop, end: false });
          if (node.dataset.sourceEnd)
            candidates.push({
              line: Number(node.dataset.sourceEnd),
              y: rect.bottom - top + scroller.scrollTop,
              end: true,
            });
        });
      candidates.sort((a, b) => a.line - b.line || Number(a.end) - Number(b.end) || a.y - b.y);
      points = [];
      let lastLine = -1,
        lastY = 0;
      for (const item of candidates) {
        if (item.line === lastLine || item.y < lastY - 1) continue;
        points.push([interpolate(metrics, item.line), item.y]);
        lastLine = item.line;
        lastY = item.y;
      }
      if (!points.length) points.push([0, 0]);
      points.push([
        Math.max(points.at(-1)[0], metrics.at(-1)[1]),
        Math.max(lastY, article.getBoundingClientRect().bottom - top + scroller.scrollTop),
      ]);
    }
    function move(target, top) {
      const maximum = Math.max(0, target.scrollHeight - target.clientHeight);
      top = Math.max(0, Math.min(maximum, top));
      if (Math.abs(target.scrollTop - top) < 1) return;
      target.scrollTo({ top, behavior: 'instant' });
      expected.set(target, target.scrollTop);
    }
    function sync(from, caret = false) {
      if (!active()) return;
      rebuild();
      const field = editor(),
        source = from === 'editor' ? field : scroller;
      const target = from === 'editor' ? scroller : field,
        axis = from === 'editor' ? 0 : 1;
      const sourceInset = from === 'editor' ? parseFloat(getComputedStyle(field).paddingTop) : 24;
      const targetInset = from === 'editor' ? 24 : parseFloat(getComputedStyle(field).paddingTop);
      const maximum = source.scrollHeight - source.clientHeight;
      let top = interpolate(points, source.scrollTop + sourceInset, axis) - targetInset;
      if (source.scrollTop <= 1) top = 0;
      else if (maximum > 1 && source.scrollTop >= maximum - 1) top = target.scrollHeight;
      move(target, top);
      if (caret && from === 'editor' && document.activeElement === field) {
        const line = field.value.slice(0, field.selectionStart).split('\n').length - 1;
        const y = interpolate(points, interpolate(metrics, line));
        if (y < scroller.scrollTop + 12 || y > scroller.scrollTop + scroller.clientHeight - 35)
          move(scroller, y - scroller.clientHeight / 3);
      }
    }
    function scroll(from, target) {
      if (expected.has(target)) {
        const top = expected.get(target);
        expected.delete(target);
        if (Math.abs(target.scrollTop - top) < 2) return;
      }
      if (paused || !active()) return;
      driver = from;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => sync(from));
    }
    scroller.addEventListener('scroll', () => scroll('preview', scroller), { passive: true });
    function mount(from = driver, caret = false) {
      cancelAnimationFrame(frame);
      paused = true;
      driver = from;
      const field = editor(),
        sourceTop = field?.scrollTop,
        previewTop = scroller.scrollTop;
      frame = requestAnimationFrame(() => {
        // A scroll between mounting and the next frame must win over the old position.
        if (field && field === editor() && Math.abs(field.scrollTop - sourceTop) > 2)
          from = 'editor';
        else if (Math.abs(scroller.scrollTop - previewTop) > 2) from = 'preview';
        paused = false;
        expected.set(scroller, scroller.scrollTop);
        if (editor()) expected.set(editor(), editor().scrollTop);
        sync(from, caret);
      });
    }
    new ResizeObserver(() => mount()).observe(scroller);
    document.fonts.ready.then(() => mount());
    return {
      bind(field) {
        field.addEventListener('scroll', () => scroll('editor', field), { passive: true });
      },
      reset() {
        paused = true;
        cancelAnimationFrame(frame);
      },
      mount,
      preview() {
        mount('editor', true);
      },
      resize() {
        mount();
      },
    };
  }
  if (typeof window !== 'undefined') window.ReaderScrollSync = { create, interpolate };
  if (typeof module !== 'undefined') module.exports = { interpolate };
})();
