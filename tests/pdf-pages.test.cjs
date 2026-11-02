const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture() {
  const intersections = [],
    resizes = [],
    frames = new Map(),
    requests = [],
    errors = [];
  let frameId = 0;
  const image = {},
    loading = { hidden: false };
  const page = {
    dataset: { pdfPage: '0' },
    getBoundingClientRect: () => ({ width: 100, height: 200, top: 10, bottom: 210 }),
    querySelector: (selector) => (selector === 'img' ? image : loading),
  };
  const secondPage = { ...page, dataset: { pdfPage: '1' } };
  const article = { querySelectorAll: () => [page, secondPage], querySelector: () => page };
  let viewport = { width: 200, height: 300, top: 0, bottom: 300 };
  const scroller = { getBoundingClientRect: () => viewport };
  let doc = { id: 'pdf', format: 'PDF', source: 'original', revision: 1 };
  const context = {
    window: {},
    IntersectionObserver: class {
      constructor(callback) {
        this.callback = callback;
        intersections.push(this);
      }
      observe() {}
      unobserve() {}
      disconnect() {
        this.disconnected = true;
      }
    },
    ResizeObserver: class {
      constructor(callback) {
        this.callback = callback;
        resizes.push(this);
      }
      observe() {}
      disconnect() {
        this.disconnected = true;
      }
    },
    requestAnimationFrame: (callback) => {
      frames.set(++frameId, callback);
      return frameId;
    },
    cancelAnimationFrame: (id) => frames.delete(id),
  };
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '../reader/web/pdf-pages.js'), 'utf8'),
    context
  );
  const loader = context.window.ReaderPDFPages.create({
    article,
    scroller,
    current: () => doc,
    native: () => ({ requestPdfPage: (...args) => requests.push(args) }),
    onError: (error) => errors.push(error),
  });
  return {
    loader,
    requests,
    errors,
    intersections,
    resizes,
    page,
    image,
    loading,
    setDocument: (value) => {
      doc = value;
    },
    hide: () => {
      viewport = { width: 0, height: 0 };
    },
    show: () => {
      viewport = { width: 200, height: 300, top: 0, bottom: 300 };
    },
    frame: () => {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((callback) => callback());
    },
  };
}

test('first page starts immediately and visible pages load without intersection callbacks', () => {
  const f = fixture();
  f.loader.mount();
  assert.deepEqual(f.requests, [['pdf', 'original', 0, 1]]);
  f.frame();
  assert.deepEqual(f.requests, [
    ['pdf', 'original', 0, 1],
    ['pdf', 'original', 1, 1],
  ]);
  f.intersections[0].callback([{ isIntersecting: true, target: f.page }]);
  f.resizes[0].callback();
  f.frame();
  assert.equal(f.requests.length, 2, 'each mounted page is requested once');
});

test('a pane mounted while hidden loads when its dimensions become visible', () => {
  const f = fixture();
  f.hide();
  f.loader.mount();
  f.frame();
  assert.equal(f.requests.length, 1, 'the first page starts even while the pane is hidden');
  f.show();
  f.resizes[0].callback();
  f.frame();
  assert.equal(f.requests.length, 2);
});

test('disposal and remounting reject callbacks and responses from the old view', () => {
  const f = fixture();
  f.loader.mount();
  f.loader.dispose();
  f.intersections[0].callback([{ isIntersecting: true, target: f.page }]);
  f.frame();
  assert.equal(f.requests.length, 1, 'disposal prevents requests beyond the eager first page');
  assert.ok(f.intersections[0].disconnected && f.resizes[0].disconnected);
  f.setDocument({ id: 'pdf', format: 'PDF', source: 'edited', revision: 2 });
  f.loader.mount();
  f.frame();
  f.loader.receive({ id: 'pdf', revision: 1, number: 0, url: 'old-image' });
  assert.equal(f.image.src, undefined);
  f.loader.receive({ id: 'pdf', revision: 2, number: 0, url: 'new-image' });
  assert.equal(f.image.src, 'new-image');
  f.image.onload();
  assert.equal(f.loading.hidden, true);
});

test('a changed source cannot request or paint an image for the previous snapshot', () => {
  const f = fixture();
  f.loader.mount();
  f.setDocument({ id: 'pdf', format: 'PDF', source: 'changed', revision: 1 });
  f.frame();
  f.loader.receive({ id: 'pdf', revision: 1, number: 0, url: 'old-image' });
  assert.equal(f.requests.length, 1, 'a changed snapshot cannot request more pages');
  assert.equal(f.image.src, undefined);
});

test('render errors leave a visible page message and notify the owning view', () => {
  const f = fixture();
  f.loader.mount();
  f.loader.receive({ id: 'pdf', revision: 1, number: 0, error: 'render failed' });
  assert.equal(f.loading.textContent, 'Could not display this page');
  assert.deepEqual(f.errors, ['render failed']);
  assert.equal(f.image.src, undefined);
});
