# Changelog

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
