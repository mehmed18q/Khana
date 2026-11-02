/* Extra reading panes share the same open buffers and persistent API views. */
(() => {
  'use strict';
  function create({ documents, current, activate, api, native, settings, positions }) {
    const workspace = document.getElementById('document-workspace');
    const layout = document.getElementById('reading-layout');
    const panes = [];
    let mode = 'single',
      previousActive;

    function makePane() {
      const section = document.createElement('section');
      section.className = 'preview-pane extra-pane';
      section.setAttribute('aria-label', `Reading pane ${panes.length + 2}`);
      const header = document.createElement('div');
      header.className = 'pane-heading';
      const select = document.createElement('select');
      select.setAttribute('aria-label', 'Document in this pane');
      const focus = document.createElement('button');
      focus.textContent = 'Focus';
      focus.title = 'Use this file in the main pane';
      const scroll = document.createElement('div');
      scroll.className = 'reading-scroll';
      const article = document.createElement('article');
      article.className = 'document';
      article.tabIndex = 0;
      header.append(select, focus);
      scroll.append(article);
      section.append(header, scroll);
      workspace.append(section);
      const pane = { section, select, focus, scroll, article, id: null, rendered: null };
      pane.pdf = ReaderPDFPages.create({
        article,
        scroller: scroll,
        current: () => documents.get(pane.id),
        native,
      });
      select.onchange = () => {
        remember(pane);
        pane.id = select.value || null;
        render();
      };
      focus.onclick = () => {
        if (pane.id) activate(pane.id);
      };
      scroll.addEventListener(
        'scroll',
        () => {
          if (pane.id) positions.set(pane.id, scroll.scrollTop);
        },
        { passive: true }
      );
      article.addEventListener('click', (event) => {
        const link = event.target.closest('a');
        if (!link) return;
        event.preventDefault();
        const href = link.getAttribute('href') || '';
        if (href.startsWith('#')) {
          try {
            article
              .querySelector(`[id="${CSS.escape(decodeURIComponent(href.slice(1)))}"]`)
              ?.scrollIntoView({ block: 'start' });
          } catch {
            /* Invalid fragment. */
          }
        } else native()?.openLink(href, pane.id);
      });
      return pane;
    }
    function remember(pane) {
      if (pane.rendered) positions.set(pane.rendered.id, pane.scroll.scrollTop);
    }
    function render() {
      const active = current();
      for (const pane of panes) {
        if (pane.id === active) {
          remember(pane);
          pane.id =
            documents.has(previousActive) && previousActive !== active ? previousActive : null;
        }
        if (!documents.has(pane.id)) pane.id = null;
      }
      previousActive = active;
      const used = new Set([active, ...panes.map((pane) => pane.id)]);
      for (const pane of panes) {
        if (!pane.id) {
          pane.id = [...documents.keys()].find((id) => !used.has(id)) || null;
          used.add(pane.id);
        }
        pane.select.replaceChildren();
        const empty = new Option('Choose an open file', '');
        pane.select.append(empty);
        for (const doc of documents.values()) {
          const option = new Option(doc.name + (doc.dirty ? ' •' : ''), doc.id);
          option.disabled = doc.id !== pane.id && used.has(doc.id);
          pane.select.append(option);
        }
        pane.select.value = pane.id || '';
        pane.focus.disabled = !pane.id;
        const doc = documents.get(pane.id);
        if (
          pane.rendered !== doc ||
          pane.html !== doc?.html ||
          pane.apiSource !== doc?.apiSource ||
          pane.revision !== doc?.revision
        ) {
          remember(pane);
          pane.pdf.dispose();
          pane.rendered = doc;
          pane.html = doc?.html;
          pane.apiSource = doc?.apiSource;
          pane.revision = doc?.revision;
          pane.article.classList.toggle('openapi-document', Boolean(doc?.api && !doc.apiSource));
          pane.article.classList.toggle('pdf-document', doc?.format === 'PDF');
          if (doc?.api && !doc.apiSource) api.show(doc, pane.article);
          else {
            pane.article.innerHTML =
              doc?.html || '<p class="empty-document">Open another file to read it here.</p>';
            ReaderBidi.prepare(pane.article);
            ReaderDiagrams.mount(pane.article, {
              theme: settings().theme,
              copy: (text) => native()?.copyText(text),
            });
            pane.pdf.mount();
          }
          pane.scroll.scrollTop = positions.get(pane.id) || 0;
        } else if (doc?.api && !doc.apiSource && !pane.article.querySelector('.api-view'))
          api.show(doc, pane.article);
      }
      preferences();
    }
    function preferences() {
      for (const pane of panes) {
        ReaderBidi.apply(pane.article, settings().direction);
        ReaderDiagrams.refreshTheme(pane.article, settings().theme);
      }
    }
    function setLayout(value) {
      if (!['single', 'columns', 'rows', 'grid'].includes(value)) return;
      mode = value;
      layout.value = value;
      workspace.dataset.layout = mode;
      document.body.classList.toggle('split-reading', mode !== 'single');
      const count = mode === 'single' ? 0 : mode === 'grid' ? 3 : 1;
      while (panes.length > count) {
        const pane = panes.pop();
        remember(pane);
        pane.pdf.dispose();
        pane.section.remove();
      }
      while (panes.length < count) panes.push(makePane());
      render();
    }
    return {
      setLayout,
      render,
      preferences,
      get mode() {
        return mode;
      },
      receivePdf(result) {
        for (const pane of panes) pane.pdf.receive(result);
      },
    };
  }
  window.ReaderWorkspace = { create };
})();
