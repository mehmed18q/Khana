import js from '@eslint/js';
import globals from 'globals';

const readerGlobals = [
  'ReaderAnnotations',
  'ReaderApiRequests',
  'ReaderBidi',
  'ReaderBuilders',
  'ReaderDiagrams',
  'ReaderFileList',
  'ReaderFormatting',
  'ReaderInsertions',
  'ReaderLibrary',
  'ReaderLineNumbers',
  'ReaderOpenAPI',
  'ReaderOutline',
  'ReaderPDF',
  'ReaderPDFPages',
  'ReaderPreviewZoom',
  'ReaderScrollSync',
  'ReaderSearch',
  'ReaderSidebar',
  'ReaderSourceEditor',
  'ReaderWindowControls',
  'ReaderWorkspace',
  'QWebChannel',
  'qt',
  'mermaid',
  'SwaggerUIBundle',
];

export default [
  { ignores: ['node_modules/', 'build/', 'dist/', 'reader/web/vendor/'] },
  js.configs.recommended,
  {
    files: ['reader/web/*.js'],
    languageOptions: {
      sourceType: 'script',
      globals: {
        ...globals.browser,
        module: 'readonly', // Pure transformation modules also run in Node tests.
        ...Object.fromEntries(readerGlobals.map((name) => [name, 'readonly'])),
      },
    },
  },
  {
    files: ['tests/*.cjs', '*.mjs'],
    languageOptions: { globals: globals.node },
  },
];
