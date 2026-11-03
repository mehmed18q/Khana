# Changelog

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
