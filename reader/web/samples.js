/* Small, offline starter documents for every editable format. */
(() => {
  'use strict';
  const templates = {
    Markdown:
      '# Document title\n\nA short introduction.\n\n## Section\n\n- First item\n- Second item\n\n| Name | Value |\n| --- | --- |\n| Example | 1 |\n',
    HTML: '<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Document title</title>\n</head>\n<body>\n  <h1>Document title</h1>\n  <p>A short introduction.</p>\n</body>\n</html>\n',
    JSON: '{\n  "name": "Example",\n  "enabled": true,\n  "items": [\n    { "id": 1, "label": "First item" }\n  ]\n}\n',
    YAML: 'name: Example\nenabled: true\nitems:\n  - id: 1\n    label: First item\n',
    XML: '<?xml version="1.0" encoding="UTF-8"?>\n<document>\n  <title>Example</title>\n  <items>\n    <item id="1">First item</item>\n  </items>\n</document>\n',
    CONF: '[application]\nname = Example\nenabled = true\n\n[paths]\ndata = ./data\n',
    LOG: '2026-01-01 09:00:00 INFO Application started\n2026-01-01 09:00:01 INFO Configuration loaded\n2026-01-01 09:00:02 WARN Example warning\n',
    Word: '<h1 dir="auto">Document title</h1>\n<p dir="auto">A short introduction.</p>\n<h2 dir="auto">Section</h2>\n<ul>\n  <li>First item</li>\n  <li>Second item</li>\n</ul>\n',
  };
  const sample = (format) => templates[format] || null;
  function expand(source, start, end, format) {
    if (start !== end) return null;
    const line = source.slice(source.lastIndexOf('\n', start - 1) + 1, start),
      abbreviation = line.replace(/^[ \t]+/, '');
    if (abbreviation !== 'sample' && !(format === 'HTML' && ['doc', '!'].includes(abbreviation)))
      return null;
    return { start: start - abbreviation.length, end };
  }
  const api = { sample, expand };
  if (typeof window !== 'undefined') window.ReaderSamples = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
