/* One page-loading lifecycle for the main preview and every extra reading pane. */
(() => {
  'use strict';
  function create({ article, scroller, current, native, onError = () => {} }) {
    const preloadMargin = 600;
    let mounted = null,
      observer,
      resizeObserver,
      frame;

    function dispose() {
      mounted = null;
      observer?.disconnect();
      resizeObserver?.disconnect();
      cancelAnimationFrame(frame);
    }

    function isCurrent(snapshot) {
      const doc = current();
      return (
        mounted === snapshot &&
        doc?.id === snapshot.id &&
        doc.revision === snapshot.revision &&
        doc.source === snapshot.source
      );
    }

    function mount() {
      dispose();
      const doc = current();
      if (doc?.format !== 'PDF') return;
      const snapshot = { id: doc.id, source: doc.source, revision: doc.revision };
      mounted = snapshot;
      const requested = new Set();
      function request(page) {
        if (!isCurrent(snapshot) || requested.has(page) || !native()?.requestPdfPage) return;
        requested.add(page);
        observer.unobserve(page);
        native().requestPdfPage(
          snapshot.id,
          snapshot.source,
          Number(page.dataset.pdfPage),
          snapshot.revision
        );
      }
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) if (entry.isIntersecting) request(entry.target);
        },
        { root: scroller, rootMargin: `${preloadMargin}px` }
      );
      const pages = [...article.querySelectorAll('.pdf-page')];
      pages.forEach((page) => observer.observe(page));
      // Paint the first page even while Chromium defers visibility callbacks.
      // Remaining pages stay lazy and follow the pane's visible area.
      if (pages.length) request(pages[0]);

      // A tab can mount while its pane is hidden or changing size. Scan again
      // after layout so the first visible page does not rely on observer timing.
      function loadVisible() {
        if (!isCurrent(snapshot)) return;
        const viewport = scroller.getBoundingClientRect();
        if (!viewport.width || !viewport.height) return;
        for (const page of pages) {
          const bounds = page.getBoundingClientRect();
          if (
            bounds.width &&
            bounds.height &&
            bounds.bottom >= viewport.top - preloadMargin &&
            bounds.top <= viewport.bottom + preloadMargin
          )
            request(page);
        }
      }
      resizeObserver = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(loadVisible);
      });
      resizeObserver.observe(scroller);
      frame = requestAnimationFrame(loadVisible);
    }

    function receive(result) {
      const snapshot = mounted;
      if (
        !snapshot ||
        !isCurrent(snapshot) ||
        result.id !== snapshot.id ||
        result.revision !== snapshot.revision
      )
        return;
      const page = article.querySelector(`[data-pdf-page="${result.number}"]`);
      if (!page) return;
      const loading = page.querySelector('.pdf-loading');
      if (result.error) {
        loading.textContent = 'Could not display this page';
        onError(result.error);
        return;
      }
      const img = page.querySelector('img');
      img.onload = () => {
        if (isCurrent(snapshot)) loading.hidden = true;
      };
      img.src = result.url;
    }

    return { mount, receive, dispose };
  }
  window.ReaderPDFPages = { create };
})();
