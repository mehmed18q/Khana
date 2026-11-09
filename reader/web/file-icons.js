/* Recognizable format marks, shared by tabs, the library and reading headers. */
(() => {
  'use strict';
  const marks = {
    markdown: [
      'Markdown',
      '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M5 16V8l3 4 3-4v8m4-8v8m-2-2 2 2 2-2"/>',
    ],
    text: ['Text', '<path d="M4 5h16M8 5v14m-3 0h6M14 11h6m-6 4h6m-6 4h4"/>'],
    html: ['HTML', '<path d="m3 3 2 17 7 2 7-2 2-17Zm5 5-3 4 3 4m8-8 3 4-3 4m-3-9-2 10"/>'],
    json: [
      'JSON',
      '<path d="M8 3H6v6l-3 3 3 3v6h2m8-18h2v6l3 3-3 3v6h-2"/><circle cx="10" cy="9" r="1"/><circle cx="14" cy="15" r="1"/>',
    ],
    yaml: [
      'YAML',
      '<path d="m3 4 4 5 4-5M7 9v11m7-14h7m-7 6h7m-7 6h7"/><circle cx="14" cy="6" r=".5"/><circle cx="14" cy="12" r=".5"/><circle cx="14" cy="18" r=".5"/>',
    ],
    log: [
      'Log',
      '<rect x="2" y="3" width="20" height="18" rx="3"/><path d="m6 8 3 3-3 3m6 0h6M6 18h12"/>',
    ],
    conf: [
      'Configuration',
      '<path d="M5 3v4m0 4v10M12 3v10m0 4v4M19 3v2m0 4v12"/><rect x="2" y="7" width="6" height="4" rx="1"/><rect x="9" y="13" width="6" height="4" rx="1"/><rect x="16" y="5" width="6" height="4" rx="1"/>',
    ],
    xml: ['XML', '<path d="m7 6-5 6 5 6m10-12 5 6-5 6M14 3l-4 18"/>'],
    word: [
      'Word',
      '<path d="M9 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H9m4-14h5m-5 5h5m-5 5h5"/><rect x="1" y="5" width="13" height="14" rx="2"/><path d="m4 9 1.5 6 2-5 2 5L11 9"/>',
    ],
    pdf: [
      'PDF',
      '<path d="M8 3h10l3 3v15H3V9m14-6v5h4"/><text x="2" y="17" stroke="none" fill="currentColor" font-size="9" font-weight="800" font-family="DejaVu Sans,sans-serif">PDF</text>',
    ],
    file: ['Document', '<path d="M14 3H5v18h14V8Zm0 0v5h5M8 12h8m-8 4h6"/>'],
  };
  function type(doc) {
    const extension = (doc?.path || doc?.name || '').split('.').pop().toLowerCase();
    if (extension === 'txt') return 'text';
    const format = (doc?.format || '').toLowerCase();
    if (marks[format]) return format;
    return (
      {
        md: 'markdown',
        markdown: 'markdown',
        mdown: 'markdown',
        mkd: 'markdown',
        htm: 'html',
        html: 'html',
        doc: 'word',
        docx: 'word',
        pdf: 'pdf',
        json: 'json',
        yaml: 'yaml',
        yml: 'yaml',
        xml: 'xml',
        log: 'log',
        conf: 'conf',
        cfg: 'conf',
        ini: 'conf',
      }[extension] || 'file'
    );
  }
  function markup(doc) {
    const kind = type(doc),
      [label, shape] = marks[kind];
    return `<svg class="file-type-icon" data-file-type="${kind}" viewBox="0 0 24 24" role="img" aria-label="${label} file"><title>${label} file</title>${shape}</svg>`;
  }
  window.ReaderFileIcons = { type, markup };
})();
