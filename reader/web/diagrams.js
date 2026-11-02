/* Offline Mermaid rendering, isolated SVG styling, and bounded render jobs. */
(() => {
  'use strict';
  const states = new WeakMap();
  let serial = Promise.resolve(),
    nextId = 0;
  const config = (theme) => ({
    startOnLoad: false,
    securityLevel: 'strict',
    suppressErrorRendering: true,
    maxTextSize: 50000,
    maxEdges: 200,
    theme: theme === 'dark' ? 'dark' : 'base',
    fontFamily: 'Reader, DejaVu Sans, sans-serif',
    htmlLabels: false,
    markdownAutoWrap: false,
    flowchart: { htmlLabels: false, useMaxWidth: false, curve: 'basis' },
    themeVariables:
      theme === 'dark'
        ? { fontFamily: 'Reader, DejaVu Sans, sans-serif' }
        : {
            fontFamily: 'Reader, DejaVu Sans, sans-serif',
            primaryColor: '#edf4ee',
            primaryTextColor: '#243f35',
            primaryBorderColor: '#739887',
            lineColor: '#648474',
            secondaryColor: '#f8edda',
            tertiaryColor: '#e7eef3',
          },
    secure: [
      'secure',
      'securityLevel',
      'startOnLoad',
      'maxTextSize',
      'maxEdges',
      'suppressErrorRendering',
      'theme',
      'themeVariables',
      'themeCSS',
      'fontFamily',
      'dompurifyConfig',
      'htmlLabels',
      'flowchart',
      'markdownAutoWrap',
    ],
  });
  // Disable Mermaid's automatic page scanner before the window load event.
  mermaid.initialize(config('light'));

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function fit(state) {
    if (!state.svg) return;
    const width = Math.max(80, state.viewport.clientWidth - 40);
    const scale = state.zoom === 'fit' ? Math.min(1, width / state.width) : state.zoom;
    state.scale = scale;
    state.svg.style.width = `${state.width * scale}px`;
    state.svg.style.height = `${state.height * scale}px`;
    state.fitButton.textContent = state.zoom === 'fit' ? 'Fit' : `${Math.round(scale * 100)}%`;
  }

  function cleanSvg(markup) {
    // Mermaid uses strict DOMPurify sanitization. Also remove navigation and
    // foreign content; graphs in a local document never gain app capabilities.
    const parsed = new DOMParser().parseFromString(markup, 'image/svg+xml');
    const svg = parsed.documentElement;
    if (svg.localName !== 'svg' || parsed.querySelector('parsererror'))
      throw new Error('Invalid diagram output.');
    svg
      .querySelectorAll(
        'script,foreignObject,image,iframe,object,embed,animate,animateMotion,animateTransform,set'
      )
      .forEach((node) => node.remove());
    for (const node of [svg, ...svg.querySelectorAll('*')]) {
      for (const attr of [...node.attributes]) {
        if (/^on/i.test(attr.name) || (attr.localName === 'href' && !attr.value.startsWith('#')))
          node.removeAttributeNode(attr);
      }
    }
    // Resolve direction for the whole label. Mermaid splits words into tspans;
    // isolating each span would reverse Persian word order across the label.
    svg.querySelectorAll('text').forEach((node) => {
      const direction = ReaderBidi.detectDirection(node.textContent, 'ltr');
      node.style.direction = direction;
      node.style.unicodeBidi = 'embed';
      // Node labels use a centered anchor. Edge labels start at a measured
      // left edge, so their RTL anchor must end there to preserve positioning.
      if (direction === 'rtl' && node.closest('.edgeLabel')) node.style.textAnchor = 'end';
    });
    svg.style.maxWidth = 'none';
    svg.style.display = 'block';
    svg.style.margin = '0 auto';
    return document.importNode(svg, true);
  }

  function queue(state, theme) {
    state.theme = theme;
    const revision = ++state.revision;
    state.frame.dataset.status = 'loading';
    state.message.textContent = 'Rendering diagram…';
    const current = () => state.frame.isConnected && revision === state.revision;
    // A serial queue avoids Mermaid's shared config racing across documents.
    serial = serial
      .catch(() => {})
      .then(async () => {
        if (!current()) return;
        try {
          if (state.source.length > 50000)
            throw new Error('The diagram exceeds the 50,000-character limit.');
          await document.fonts.ready;
          if (!current()) return;
          mermaid.initialize(config(theme));
          const { svg: markup } = await mermaid.render(`khana-diagram-${++nextId}`, state.source);
          if (!current()) return;
          const svg = cleanSvg(markup),
            viewBox = svg.viewBox.baseVal;
          if (!viewBox.width || !viewBox.height)
            throw new Error('The diagram has no visible steps.');
          state.width = viewBox.width;
          state.height = viewBox.height;
          state.svg = svg;
          state.shadow.replaceChildren(svg);
          const title = svg.querySelector('title')?.textContent;
          state.caption.textContent = title || 'Diagram';
          state.caption.dir = 'auto';
          svg.setAttribute('role', 'img');
          if (!svg.hasAttribute('aria-labelledby'))
            svg.setAttribute('aria-label', title || 'Mermaid diagram');
          state.frame.dataset.status = 'ready';
          state.frame.dataset.theme = theme;
          state.controls.forEach((button) => {
            button.disabled = false;
          });
          fit(state);
        } catch (error) {
          if (!current()) return;
          state.frame.dataset.status = 'error';
          state.shadow.replaceChildren();
          state.svg = null;
          state.controls.forEach((button) => {
            button.disabled = true;
          });
          state.message.textContent = `Could not render this diagram. Edit its Mermaid source and try again. ${String(error.message || error).slice(0, 600)}`;
          state.details.open = true;
        }
      });
  }

  function mount(article, { theme = 'light', copy = () => {} } = {}) {
    article.querySelectorAll('pre > code.language-mermaid').forEach((code) => {
      const source = code.textContent;
      const frame = element('figure', 'diagram-frame'),
        toolbar = element('div', 'diagram-toolbar');
      for (const key of ['sourceLine', 'sourceEnd'])
        if (code.parentElement.dataset[key]) frame.dataset[key] = code.parentElement.dataset[key];
      const caption = element('figcaption', 'diagram-caption', 'Diagram'),
        actions = element('div', 'diagram-actions');
      const viewport = element('div', 'diagram-viewport'),
        surface = element('div', 'diagram-surface');
      const message = element('div', 'diagram-message');
      message.setAttribute('role', 'status');
      const details = element('details', 'diagram-source'),
        pre = element('pre'),
        plainCode = element('code', '', source);
      pre.dir = 'ltr';
      plainCode.dir = 'ltr';
      pre.append(plainCode);
      details.append(element('summary', '', 'Mermaid source'), pre);
      const button = (text, label, callback) => {
        const result = element('button', '', text);
        result.type = 'button';
        result.title = label;
        if (text === '+' || text === '−') result.setAttribute('aria-label', label);
        result.onclick = callback;
        actions.append(result);
        return result;
      };
      const state = {
        frame,
        source,
        caption,
        viewport,
        surface,
        message,
        details,
        revision: 0,
        zoom: 'fit',
        scale: 1,
      };
      const zoom = (factor) => {
        state.zoom = Math.max(0.15, Math.min(3, state.scale * factor));
        fit(state);
      };
      const minus = button('−', 'Zoom out', () => zoom(1 / 1.25));
      state.fitButton = button('Fit', 'Fit diagram to width', () => {
        state.zoom = 'fit';
        fit(state);
      });
      const plus = button('+', 'Zoom in', () => zoom(1.25));
      button('Copy source', 'Copy Mermaid source', () => copy(source));
      state.controls = [minus, state.fitButton, plus];
      state.controls.forEach((button) => {
        button.disabled = true;
      });
      toolbar.append(caption, actions);
      viewport.append(surface, message);
      frame.append(toolbar, viewport, details);
      code.parentElement.replaceWith(frame);
      // SVG styles never enter the app's stylesheet scope and app icon styles
      // never shrink the graph. A WeakMap lets detached previews be collected.
      state.shadow = surface.attachShadow({ mode: 'open' });
      states.set(frame, state);
      queue(state, theme);
    });
  }
  function refreshTheme(article, theme) {
    article.querySelectorAll('.diagram-frame').forEach((frame) => {
      const state = states.get(frame);
      if (state && state.theme !== theme) queue(state, theme);
    });
  }
  function resize(article) {
    article.querySelectorAll('.diagram-frame').forEach((frame) => {
      const state = states.get(frame);
      if (state) fit(state);
    });
  }
  window.ReaderDiagrams = { mount, refreshTheme, resize };
})();
