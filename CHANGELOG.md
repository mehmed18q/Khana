# Changelog

## 0.12.0 — 2026-11-10

- Add Exit, Cancel and Stay in background choices when closing a window, with a system tray menu to restore windows or exit after checking unsaved changes.
- Reduce source editing, context-menu and undo/redo delays with cached source indexes and measurements, and spelling highlights limited to visible lines. Preserve the selected text highlight while its context menu is open.
- Align spelling underlines with mixed RTL/LTR text, prioritize common typo corrections, cancel obsolete checks, and reject late spelling work after a window closes.
- Keep the current heading selected in On this page while reading or editing, without moving the outline's own scroll position.
- Show loading messages and notifications at the bottom center, including the filename when opening one document.
- Add file size, line/column, word count and source line count to the footer; hide empty category folders.
- Add undoable format samples through Insert sample, Ctrl+Shift+Space and sample + Tab; HTML also supports doc + Tab and ! + Tab.
- Show table and flowchart editing controls only in Edit & Preview.
- Add rotating local application logs, Python crash traces, renderer error reporting and slow-operation diagnostics, accessible through Logs in the footer.
- Publish the Ubuntu 24.04+ amd64 package as `0.12.0-1` through the existing signed APT repository.

## 0.11.0 — 2026-11-10

- Add an Arabic interface with right-to-left layout, translated menus and dialogs, and a flag in the language picker.
- Add offline Arabic spelling alongside Persian and English, including vocalized words, correction suggestions, and document/global ignore options.
- Show clickable folder breadcrumbs beneath the document name. Each segment opens its folder; the path follows tab changes, renames and Save As.
- Add a GitHub repository icon and link the developer's name to their GitHub profile.
- Publish the Ubuntu 24.04+ amd64 package as `0.11.0-1` through the existing signed APT repository.

## Packaging 0.10.0-2 — 2026-11-10

- Rebuild on Ubuntu 24.04 amd64 for compatibility with Ubuntu 24.04 and newer; reject bundles requiring GLIBC newer than 2.39.
- Add an isolated Docker build and packaged GUI compatibility check, plus signed APT repository generation and GitHub Pages publication workflow.
- Keep the application version at 0.10.0; the Debian packaging revision advances from 1 to 2.

## 0.10.0 — 2026-11-10

- Faster Find and navigation: linear rendered-text indexing, cached search ranges and scroll maps, binary interpolation, and visible-only reading gutters. Typing no longer rebuilds library and annotation lists.
- Equivalent Persian, Arabic and Latin digits in Find and Replace.
- Persistent Persian/English interface with mirrored layout, an icon and flag language menu, and icons in the new-document format menu.
- Source editing context menus and offline Persian/English spelling, with a header toggle, suggestions, and persistent document/global ignore scopes.
- Reopen tables and generated flowcharts for editing; reorder table rows/columns by dragging or keyboard, copy/paste rows, and navigate cells with arrow keys. Complex structures retain a source-editing fallback.

## 0.9.0 — 2026-11-09

### Added

- Distinct format icons in Open Files, Library and reading headers, including
  separate plain-text and Markdown marks.
- Light, dark and automatic system appearance, with six color palettes and
  live theme updates shared across open windows.
- A persistent compact header that folds the top reading controls into a small
  filename strip while preserving the sidebar, window state and editor.
- Offline LaTeX math rendering for inline and display Markdown equations, with
  isolated left-to-right formulas inside Persian prose, live previews and split panes.
- File context menus in Open Files and Library, with native file copy/cut, path
  and name copying, containing folders, new windows, saving and closing.
- Star, pin and manual ordering actions shared across lists and windows, with
  persistent ordering and migration of existing reading libraries.
- A sidebar minimize/expand button that remembers its state and restores the
  previous sidebar width and section sizes.
- Named, ordered document categories shared by Open Files and Library, with
  persistent membership, collapsible groups and drag-and-drop category moves.
- Ctrl/Command multi-selection with bulk copy/cut, category destination selection,
  star/pin actions and closing that respects unsaved-change cancellation.
- File renaming from both context menus, preserving edits, annotations and
  organization while protecting existing files from replacement.
- Context-menu split layouts matching the header, including splitting selected
  open documents into two or four reading panes.

## 0.8.0 — 2026-11-07

### Added

- Find and Find All in reading and editing modes, with a separate results dialog
  that focuses the selected match in the main document or source editor.
- Undoable Replace and Replace All for source text, opened with Ctrl+H or the
  expandable replacement row beside the search field.
- Match case and Unicode-aware Whole word icon controls inside the search field,
  including Persian letters and half-spaces, plus F3 / Shift+F3 navigation.

### Fixed

- Editing searches now use the latest source buffer, including unsaved changes
  and source content omitted from the rendered preview.
- Reading searches correctly handle inline formatting, displayed HTML whitespace,
  Unicode offsets, hidden content and Swagger endpoint text.
- Search navigation keeps its position across preview updates, and result counts
  and replacement operations no longer stop at 2,000 matches.

## 0.7.0 — 2026-11-03

### Added

- Editor line numbers with the current line highlighted, aligned with wrapped
  Persian and English text and updated while typing and scrolling.
- Source line numbers beside rendered reading content and outline headings,
  including split reading panes. PDFs retain their page-based presentation.
- Go to line with Ctrl+G in both reading and editing modes, preserving the current
  mode and accepting English, Persian and Arabic digits.
- Reading fullscreen with Ctrl+Shift+F, hiding the sidebar and application
  toolbars. Escape, F11 or the revealable exit button restores the previous window.
- Horizontal sidebar resizing with pointer and keyboard controls, a remembered
  width, and bounds that keep the document usable in smaller windows.

### Changed

- Shared source measurements keep line numbers, navigation and preview scrolling
  aligned without rendering an editor gutter row for every line of large files.

## 0.6.0 — 2026-11-02

### Added

- Independent document windows, tab drag-and-drop and a detach button, preserving
  unsaved text and view state while moving documents between windows.
- Two- and four-pane reading layouts with a document selector in each pane.
- Single-instance file routing that activates an already open document or opens
  new files in the most recently used window.
- Resizable, collapsible sidebar sections with remembered proportions.

### Fixed

- Native tab dragging could crash in Qt/PySide's event-filter bindings.
- Tab transfers, late worker results and reopening documents could interfere with
  buffer ownership, editor locking or asynchronous preview results.
- Library changes across windows could leave stale views or remove annotations
  for a document still open in another window.
- Hidden API views could retain requests after their definition changed; the
  first PDF page could depend on delayed browser visibility notifications.

### Changed

- Split native window, bridge, worker and workspace responsibilities; extracted
  focused frontend modules and shared PDF loading.
- Added architecture documentation, code-style checks and expanded regression
  coverage, including the real native Qt drag loop.
- Centralized the displayed application version and rejected installer builds
  that would package an executable with a different version.
