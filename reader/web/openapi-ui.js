/* Swagger owns its DOM inside a shadow root; reader styles never touch it. */
(() => {
  'use strict';
  let bundle;
  const contentRoot = (article) => article.querySelector('.swagger-host')?.shadowRoot || article;
  function loadBundle() {
    if (!bundle)
      bundle = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'vendor/swagger-ui-bundle.js';
        script.onload = () => resolve(window.SwaggerUIBundle);
        script.onerror = () => {
          script.remove();
          bundle = null;
          reject(new Error('Could not load Swagger UI.'));
        };
        document.head.append(script);
      });
    return bundle;
  }
  function scopeOf(spec) {
    return JSON.stringify([
      spec.host,
      spec.basePath,
      spec.schemes,
      spec.servers,
      spec.securityDefinitions,
      spec.components?.securitySchemes,
      Object.entries(spec.paths || {}).flatMap(([path, item]) => [
        ...(item?.servers ? [[path, item.servers]] : []),
        ...Object.entries(item || {})
          .filter(([, operation]) => operation?.servers)
          .map(([method, operation]) => [path, method, operation.servers]),
      ]),
    ]);
  }
  function createView({ article, theme, direction, ready, openLink, requests }, initial) {
    const states = new WeakMap();
    let host,
      root,
      ui,
      mount,
      observer,
      frame,
      revision = 0,
      previousBlocks = [],
      loaded = false,
      mountedDoc,
      state,
      cancelButton;
    const unsubscribe = requests.onChange(() => {
      if (!cancelButton || !mountedDoc) return;
      const count = requests.count(mountedDoc.id);
      cancelButton.disabled = !count;
      cancelButton.textContent = count ? `Cancel requests (${count})` : 'Cancel requests';
    });
    function dispose() {
      revision++;
      observer?.disconnect();
      observer = null;
      cancelAnimationFrame(frame);
      if (ui && state) state.authorized = ui.authSelectors.authorized().toJS();
      if (mountedDoc) requests.cancel(mountedDoc.id);
      // Unmount React children before removing their container.
      if (ui && mount) ui.render(mount, 'KhanaEmpty');
      ui = null;
      host = root = mount = null;
      previousBlocks = [];
      loaded = false;
      mountedDoc = state = cancelButton = null;
    }
    function preferences() {
      if (!host) return;
      host.dataset.theme = theme();
      root
        .querySelectorAll(
          '.renderedMarkdown p,.renderedMarkdown li,.opblock-summary-description,.info .title'
        )
        .forEach((node) => {
          node.dir =
            direction() === 'smart'
              ? ReaderBidi.detectDirection(node.textContent, 'ltr')
              : direction();
        });
    }
    function decorate(doc) {
      if (!root) return;
      preferences();
      const blocks = [...root.querySelectorAll('.opblock')];
      // Inline specifications do not always invoke Swagger's onComplete callback.
      // Wait for its first rendered operations before restoring the transferred store.
      if (ui && initial?.scope === state.scope && initial.store && root.querySelector('.info')) {
        const saved = initial;
        initial = null;
        for (const [key, value] of Object.entries(saved.store))
          ui[`${key}Actions`]?.khanaRestore(value);
        // Swagger keys layout.shown with Immutable Lists. Plain JSON map keys
        // lose their identity, so rebuild these through the public layout action.
        for (const [key, shown] of saved.layoutShown || []) ui.layoutActions.show(key, shown);
        frame = requestAnimationFrame(() => decorate(doc));
        return;
      }
      for (const block of blocks) {
        const path = block.querySelector('.opblock-summary-path')?.getAttribute('data-path');
        const method = block
          .querySelector('.opblock-summary-method')
          ?.textContent.trim()
          .toLowerCase();
        const operation = doc.api.operations.find(
          (item) => item.path === path && item.method === method
        );
        if (!operation) continue;
        block.id = operation.id;
        block.dataset.apiOperation = `${method.toUpperCase()} ${path}`;
        block.dataset.sourceLine = operation.line;
        block.dataset.sourceEnd = operation.end;
      }
      if (
        !loaded ||
        blocks.length !== previousBlocks.length ||
        blocks.some((block, i) => block !== previousBlocks[i])
      ) {
        const first = !loaded;
        loaded = true;
        previousBlocks = blocks;
        doc.apiRendering = false;
        ready(doc, first);
      }
    }
    async function show(doc) {
      dispose();
      const token = revision;
      mountedDoc = doc;
      const scope = scopeOf(doc.api.spec);
      state = states.get(doc);
      if (!state || state.scope !== scope) {
        state = {
          scope,
          authorized: initial?.scope === scope ? initial.authorized || {} : {},
          baseURL: initial?.scope === scope ? initial.baseURL || '' : '',
        };
        states.set(doc, state);
      }
      article.replaceChildren();
      const notice = document.createElement('div');
      notice.className = 'api-notice';
      notice.dir = 'ltr';
      notice.textContent =
        `${doc.api.label} · Use Try it out and Execute to send a request. Authorize adds credentials for secured operations.` +
        (doc.api.externalRefs
          ? ' · External $ref files are not loaded. Use a bundled definition for complete models.'
          : '');
      host = document.createElement('div');
      host.className = 'swagger-host';
      host.dir = 'ltr';
      root = host.attachShadow({ mode: 'open' });
      for (const path of ['vendor/swagger-ui.css', 'openapi-shadow.css']) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = path;
        root.append(link);
      }
      mount = document.createElement('div');
      mount.className = 'swagger-mount';
      root.append(mount);
      const loading = document.createElement('p');
      loading.textContent = 'Loading API documentation…';
      mount.append(loading);
      article.append(notice, host);
      preferences();
      const settings = document.createElement('details');
      settings.className = 'api-request-settings';
      const summary = document.createElement('summary');
      summary.textContent = 'Request settings';
      const form = document.createElement('form');
      form.className = 'api-server-form';
      const label = document.createElement('label');
      label.htmlFor = 'api-base-url';
      label.textContent = 'Server URL override';
      const server = document.createElement('input');
      server.id = 'api-base-url';
      server.type = 'url';
      server.autocomplete = 'off';
      server.placeholder = 'Use the servers defined in this document';
      server.value = state.baseURL;
      const apply = document.createElement('button');
      apply.type = 'submit';
      apply.textContent = 'Apply';
      const help = document.createElement('p');
      help.textContent =
        'Optional full base URL, including /v1 if needed. Changing it clears authorization. Credentials stay in memory until this document is closed.';
      const status = document.createElement('p');
      status.className = 'api-request-status';
      status.setAttribute('role', 'status');
      cancelButton = document.createElement('button');
      cancelButton.type = 'button';
      cancelButton.textContent = 'Cancel requests';
      cancelButton.disabled = true;
      cancelButton.onclick = () => requests.cancel(doc.id);
      form.append(label, server, apply);
      settings.append(summary, form, help, cancelButton, status);
      root.insertBefore(settings, mount);
      form.onsubmit = (event) => {
        event.preventDefault();
        let value = server.value.trim();
        try {
          if (value) {
            const url = new URL(value);
            if (
              !['http:', 'https:'].includes(url.protocol) ||
              url.username ||
              url.password ||
              url.search ||
              url.hash
            )
              throw new Error();
            value = url.href.replace(/\/$/, '');
          }
        } catch {
          status.textContent =
            'Enter an HTTP or HTTPS base URL without credentials, a query, or a fragment.';
          return;
        }
        if (value !== state.baseURL) {
          requests.cancel(doc.id);
          state.baseURL = value;
          state.authorized = {};
          ui?.authActions.restoreAuthorization({ authorized: {} });
        }
        status.textContent = value
          ? 'Server override applied. Authorization cleared when the server changed.'
          : 'Using servers from the document.';
      };
      root.addEventListener('click', (event) => {
        const link = event.target.closest('a');
        if (!link) return;
        event.preventDefault();
        const href = link.getAttribute('href') || '';
        if (/^https?:|^mailto:/i.test(href)) openLink(href);
      });
      try {
        const SwaggerUI = await loadBundle();
        if (revision !== token) return;
        mount.replaceChildren();
        observer = new MutationObserver(() => {
          cancelAnimationFrame(frame);
          frame = requestAnimationFrame(() => decorate(doc));
        });
        observer.observe(mount, { childList: true, subtree: true });
        const executeFetch = (url, request) =>
          requests.fetch(doc.id, url, request, () => revision === token);
        const plugin = (system) => {
          const React = system.React;
          function OAuthToken(props) {
            const [value, setValue] = React.useState('');
            const authorized = props.authSelectors.authorized().has(props.name);
            return React.createElement(
              'div',
              { className: 'api-oauth-token' },
              React.createElement('h4', null, `${props.name} (OAuth2 access token)`),
              React.createElement(
                'p',
                null,
                'Paste an existing access token. Browser sign-in and token refresh are not supported.'
              ),
              authorized
                ? React.createElement('p', null, 'Authorized')
                : React.createElement('input', {
                    type: 'password',
                    autoComplete: 'off',
                    'aria-label': 'OAuth2 access token',
                    value,
                    onChange: (event) => setValue(event.target.value),
                  }),
              React.createElement(
                'button',
                {
                  type: 'button',
                  className: 'btn authorize',
                  disabled: !authorized && !value.trim(),
                  onClick: () => {
                    if (authorized) props.authActions.logout([props.name]);
                    else
                      props.authActions.authorizeOauth2({
                        auth: { name: props.name, schema: props.schema.toJS(), scopes: [] },
                        token: { access_token: value.trim(), token_type: 'Bearer' },
                      });
                    setValue('');
                  },
                },
                authorized ? 'Logout' : 'Authorize'
              )
            );
          }
          const statePlugins = Object.fromEntries(
            ['spec', 'layout', 'auth', 'oas3'].map((key) => [
              key,
              {
                actions: { khanaRestore: (payload) => ({ type: `KHANA_RESTORE_${key}`, payload }) },
                reducers: {
                  [`KHANA_RESTORE_${key}`]: (previous, action) => system.Im.fromJS(action.payload),
                },
              },
            ])
          );
          statePlugins.spec.wrapActions = {
            executeRequest: (original) => (args) =>
              original({ ...args, userFetch: executeFetch, baseURL: state.baseURL || undefined }),
          };
          return { components: { KhanaEmpty: () => null, oauth2: OAuthToken }, statePlugins };
        };
        ui = SwaggerUI({
          domNode: mount,
          spec: doc.api.spec,
          url: '',
          validatorUrl: null,
          supportedSubmitMethods: [
            'get',
            'head',
            'post',
            'put',
            'patch',
            'delete',
            'options',
            'trace',
          ],
          tryItOutEnabled: false,
          persistAuthorization: false,
          displayRequestDuration: true,
          deepLinking: false,
          filter: true,
          docExpansion: 'list',
          virtualized: false,
          defaultModelsExpandDepth: 1,
          defaultModelExpandDepth: 1,
          syntaxHighlight: { activated: false },
          requestInterceptor: (request) => {
            if (request.userFetch !== executeFetch || request.loadSpec)
              throw new Error('External references and automatic network requests are disabled.');
            return request;
          },
          plugins: [plugin],
          onComplete: () => {
            if (revision === token) decorate(doc);
          },
        });
        ui.authActions.restoreAuthorization({ authorized: state.authorized });
      } catch (error) {
        if (revision !== token) return;
        mount.replaceChildren();
        const message = document.createElement('p');
        message.textContent = `${error.message} Choose Source to read the document.`;
        mount.append(message);
        doc.apiRendering = false;
        ready(doc, true);
      }
    }
    return {
      show,
      dispose() {
        dispose();
        unsubscribe();
      },
      preferences,
      resume(doc) {
        preferences();
        decorate(doc);
      },
      snapshot(full = true) {
        if (!state) return initial || null;
        const runtime = ui?.getState(),
          store = runtime?.toJS();
        const layoutShown = runtime
          ?.getIn(['layout', 'shown'])
          ?.entrySeq()
          .toArray()
          .map(([key, value]) => [key.toJS ? key.toJS() : key, value]);
        if (store?.layout) delete store.layout.shown;
        return {
          scope: state.scope,
          baseURL: state.baseURL,
          authorized: ui?.authSelectors.authorized().toJS() || state.authorized,
          layoutShown: full ? layoutShown : undefined,
          store:
            full && store
              ? Object.fromEntries(
                  ['spec', 'layout', 'auth', 'oas3']
                    .filter((key) => store[key])
                    .map((key) => [key, store[key]])
                )
              : undefined,
        };
      },
    };
  }
  function create(options) {
    const views = new Map();
    function update(doc) {
      const entry = views.get(doc.id);
      if (!doc.api) delete doc.apiInitial;
      if (entry && (entry.doc !== doc || entry.api !== doc.api)) {
        const saved = doc.api ? entry.view.snapshot(false) : null;
        entry.view.dispose();
        entry.container.remove();
        views.delete(doc.id);
        doc.apiInitial = saved;
      }
    }
    return {
      update,
      show(doc, target = options.article) {
        update(doc);
        let entry = views.get(doc.id);
        if (!entry) {
          const container = document.createElement('div');
          container.className = 'api-view';
          entry = { doc, api: doc.api, container };
          entry.view = createView(
            {
              ...options,
              article: container,
              openLink: (href) => options.openLink(href, doc.id),
              ready: (item, first) => {
                if (options.current() === item && options.article.contains(container))
                  options.ready(item, first);
              },
            },
            doc.apiInitial
          );
          delete doc.apiInitial;
          views.set(doc.id, entry);
          target.replaceChildren(container);
          entry.view.show(doc);
        } else {
          target.replaceChildren(entry.container);
          doc.apiRendering = false;
          entry.view.resume(doc);
        }
      },
      snapshot: (id) => views.get(id)?.view.snapshot(),
      setMoving(id, moving) {
        const entry = views.get(id);
        if (entry) entry.container.inert = moving;
      },
      dispose(id) {
        const entry = views.get(id);
        if (entry) {
          entry.view.dispose();
          entry.container.remove();
          views.delete(id);
        }
      },
      preferences() {
        for (const entry of views.values()) entry.view.preferences();
      },
    };
  }
  window.ReaderOpenAPI = { create, contentRoot };
})();
