# Mermaid browser bundle

- Package: `mermaid` 11.12.2
- File: `mermaid.min.js`, the complete browser bundle (no external dynamic imports)
- Upstream: https://github.com/mermaid-js/mermaid
- Distribution: https://cdn.jsdelivr.net/npm/mermaid@11.12.2/dist/mermaid.min.js
- License: MIT; copied from https://cdn.jsdelivr.net/npm/mermaid@11.12.2/LICENSE into `MERMAID-LICENSE.txt`
- API reference: https://mermaid.js.org/config/usage.html

The bundle is checked into the application folder for offline use. It requires no npm install or network connection at runtime. Its upstream version is pinned; upgrades must be verified with `tests/builders_smoke.py`, especially SVG sanitization, configuration directives, mixed Persian/English text, and WebEngine compatibility.

# KaTeX browser bundle

- Package: `katex` **0.19.1**.
- Upstream: https://github.com/KaTeX/KaTeX
- Distribution: https://registry.npmjs.org/katex/-/katex-0.19.1.tgz
- Files: unmodified `dist/katex.min.js`, `dist/katex.min.css`, and `dist/fonts/` under `katex/`.
- License: MIT, included as `katex/LICENSE`.
- Configuration reference: https://katex.org/docs/options.html

Markdown math tokens are parsed before other inline formatting, then rendered locally with `trust: false`, bounded macro expansion and dimensions, and HTML plus accessible MathML. No CDN or runtime network access is used. Check upgrades with `tests/math_smoke.py`, including Persian prose, RTL/LTR controls, fractions, display equations, live previews and split panes.

# Swagger UI browser bundle

- Package: `swagger-ui-dist` **5.34.0**, loaded locally on the first API preview.
- Upstream: https://github.com/swagger-api/swagger-ui/releases/tag/v5.34.0
- Distribution base: `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.0/`
- Files: `swagger-ui-bundle.js`, `swagger-ui.css`, `LICENSE` (saved as `SWAGGER-UI-LICENSE.txt`), and `swagger-ui-bundle.js.LICENSE.txt` (dependency notices).
- License: Apache-2.0 plus the notices in `swagger-ui-bundle.js.LICENSE.txt`.
- CSS adaptation: replace every `html.dark-mode` selector with `:host([data-theme=dark])` for the isolated preview's shadow root. No JavaScript modifications.
- Configuration reference: https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/

SHA-256 checksums of the checked-in files (including the adapted CSS):

```text
3f6abf70480db7e07914df4c98a77385f22ea585eaf457a3e6415ba0eae2d167  swagger-ui-bundle.js
516e1fac53ef1308d252cc3e8337f2f1ccee087df6488301f26fe51334075194  swagger-ui.css
cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30  SWAGGER-UI-LICENSE.txt
e5a4792feaa5332dfba37f1d7adf84308b93b4f2d8da0569a9f48a3cb61c969b  swagger-ui-bundle.js.LICENSE.txt
```

No CDN, online validator or external `$ref` fetching is used at runtime. Only explicit **Execute** actions use the native HTTP bridge through a fetch-compatible `userFetch` override; all other requests remain blocked. The plugin uses pinned Swagger UI `spec.executeRequest`, `authSelectors.authorized`, `authActions.restoreAuthorization`, and an OAuth2 token-entry component. Verify upgrades with `tests/openapi_smoke.py`, `tests/api_requests_smoke.py`, `tests/api_transport_smoke.py`, and the packaged application test, including authorization, internal references, Persian descriptions, live editing, source fallback, marks, zoom, and scrolling.
