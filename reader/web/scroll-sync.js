/* Bidirectional source/preview scroll mapping, including wrapped source lines. */
(() => {
  'use strict';
  function interpolate(points, value, axis = 0) {
    if (!points.length) return 0;
    const other = 1 - axis;
    if (value <= points[0][axis]) return points[0][other];
    let lo = 1,
      hi = points.length - 1;
    if (value > points[hi][axis]) return points[hi][other];
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (points[mid][axis] < value) lo = mid + 1;
      else hi = mid;
    }
    const a = points[lo - 1],
      b = points[lo],
      width = b[axis] - a[axis];
    return width > 0 ? a[other] + ((b[other] - a[other]) * (value - a[axis])) / width : b[other];
  }
  function create({ article, scroller, editor, current, enabled, lineNumbers }) {
    let points = [],
      metrics = [],
      frame = 0,
      paused = false,
      driver = 'preview',
      dirty = true;
    const expected = new WeakMap();
    const active = () =>
      enabled() &&
      current()?.editMode &&
      current()?.format !== 'PDF' &&
      editor() &&
      !current().previewPending &&
      !current().apiRendering;
    function rebuild() {
      if (!active()) return;
      if (!dirty) return;
      dirty = false;
      metrics = lineNumbers.metrics(editor());
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
      dirty = true;
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
      revealLine(line) {
        const field = editor();
        if (!field) return;
        move(field, lineNumbers.lineTop(field, line) - field.clientHeight / 3);
        mount('editor', true);
      },
      revealPreviewLine(line) {
        const anchors = [
          ...ReaderOpenAPI.contentRoot(article).querySelectorAll('[data-source-line]'),
        ]
          .filter((node) => !node.closest('.diagram-source'))
          .sort((a, b) => Number(a.dataset.sourceLine) - Number(b.dataset.sourceLine));
        const target =
          anchors.findLast(
            (node) => Number(node.dataset.sourceLine) <= line && node.getClientRects().length
          ) || anchors.find((node) => node.getClientRects().length);
        article.focus({ preventScroll: true });
        if (!target) {
          move(scroller, 0);
          return;
        }
        const rect = target.getBoundingClientRect(),
          start = Number(target.dataset.sourceLine),
          end = Number(target.dataset.sourceEnd),
          fraction = end > start ? Math.max(0, Math.min(1, (line - start) / (end - start))) : 0;
        move(
          scroller,
          scroller.scrollTop +
            rect.top -
            scroller.getBoundingClientRect().top +
            rect.height * fraction -
            scroller.clientHeight / 3
        );
        mount('preview');
      },
      resize() {
        mount();
      },
    };
  }
  if (typeof window !== 'undefined') window.ReaderScrollSync = { create, interpolate };
  if (typeof module !== 'undefined') module.exports = { interpolate };
})();
