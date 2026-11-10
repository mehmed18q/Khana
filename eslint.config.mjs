import js from '@eslint/js';
import globals from 'globals';

const readerGlobals = [
  'ReaderAnnotations',
  'ReaderApiRequests',
  'ReaderBidi',
  'ReaderCategories',
  'ReaderContextMenu',
  'ReaderBuilders',
  'ReaderDiagrams',
  'ReaderFileList',
  'ReaderFileIcons',
  'ReaderHeader',
  'ReaderTheme',
  'ReaderFileMenu',
  'ReaderFileSelection',
  'ReaderFormatting',
  'ReaderInsertions',
  'ReaderLibrary',
  'ReaderLineNumbers',
  'ReaderMath',
  'ReaderOpenAPI',
  'ReaderOutline',
  'ReaderPDF',
  'ReaderPDFPages',
  'ReaderPreviewZoom',
  'ReaderScrollSync',
  'ReaderSearch',
  'ReaderSidebar',
  'ReaderSourceEditor',
  'ReaderSourceText',
  'ReaderSamples',
  'ReaderDiagnostics',
  'ReaderStructures',
  'ReaderSpelling',
  'ReaderI18n',
  'ReaderPickers',
  'ReaderWindowControls',
  'ReaderWorkspace',
  'QWebChannel',
  'qt',
  'mermaid',
  'katex',
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
