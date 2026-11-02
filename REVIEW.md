# Project review — 2026-11-02

This snapshot records the project state after its directory was renamed to
`khana`. It does not restore the previous agent conversation.

## Starting state

- Application: Khana 0.5.4, a local Qt/WebEngine document reader and editor.
- Platform checked: Ubuntu 26.04.1 x86_64, Python 3.14.4, PySide6 6.12.0.
- Git branch: `master`; starting commit: `1758d9e`. At review start, the local
  branch was one commit ahead of the locally recorded `origin/master`.
- Existing staged and unstaged work added single-instance IPC, multiple windows,
  tab transfers, reading panes, retained Swagger views, and sidebar resizing.
  Those changes were preserved. This review did not create a commit or push.
- Source configuration and the library live in `.local/`. Packaged builds use
  the user's XDG configuration directory. Tests use temporary configurations.
- Checked 49 virtual-environment and IDE text files: no missing project paths
  remained after the rename. Installed dependencies pass `pip check`.

## Confirmed defects fixed

| Problem | Correction | Regression coverage |
| --- | --- | --- |
| Removing a library entry from one window could delete notes for a document still open in another. | Check ownership across all windows, including queued opens. | `test_workspace.py` |
| Library changes left stars and annotations stale in other windows. | Refresh each window after a successful library mutation. | `test_workspace.py`, `workspace_smoke.py` |
| Opening the same file in two windows before loading completed created duplicate buffers. | Reserve paths during loading and route opens to their existing window. | `test_workspace.py` |
| Save As could replace a file still loading in another window. | Check pending loads across all windows before offering replacement. | `test_workspace.py` |
| Save/reload shortcuts could act on a moving tab; a rejected quit unlocked its editor. | Guard native and UI operations during transfer and preserve the editor lock after a rejected quit. | `test_workspace.py`, `workspace_smoke.py` |
| Editing an API definition and switching tabs before preview completion left old requests running. | Invalidate retained API views as soon as their definition changes, including hidden tabs. Preserve authorization only within the existing scope rules. | `api_requests_smoke.py` |
| A delayed close event could clear the table/flowchart builder's new context after reopening, making insertion do nothing. | Ignore stale close events while the dialog is open again. | `builders_smoke.py` simulates the delayed event before insertion. |

The packaging test harness now isolates its temporary socket directory as well
as its configuration directory, so single-instance forwarding cannot send test
files to an ordinary running Khana instance.

## Validation

- Python unit tests: 47 passed, including five new cross-window regressions.
- JavaScript: all five Node test files passed.
- All 12 source integration checks passed in their latest runs: desktop,
  workspace, sidebar, API requests, API transport, OpenAPI, editor, builders,
  library, formats, zoom, and beautify. The workspace, API, and builder checks
  include the new regressions described above.
- Python/JavaScript syntax, HTML IDs, local UI assets, dependency consistency,
  CLI version, and whitespace checks passed.
- Fresh portable and Debian builds passed `bundle_smoke.py` and `deb_smoke.py`,
  including Wayland/X11 identity, persistence, API requests, Word import/export,
  and PDF rendering/editing/saving. Both generated SHA-256 checksums pass.
  Outputs: `dist/Khana` and `dist/khana_0.5.4-1_amd64.deb`. Nothing was installed
  or published. The binaries present at review start predated the working tree.

An intermittent PDF issue remains unconfirmed: `formats_smoke.py` twice timed
out waiting for its first PDF image during runs overlapping packaging builds.
The separate rerun and the packaged PDF checks passed. The failing DOM had an
image without a source and no pending native PDF tasks. Additional DOM and
response diagnostics remain in the test; the cause of those timeouts has not
been established, so this review does not claim to have fixed that instability.

Detailed logs are written to `artifacts/review/`, which is gitignored. The
latest results, including successful reruns, are in
`artifacts/review/final-results.json`. Original failing logs are retained there
as well. Reproducible test commands are listed under **Checks** in `README.md`.

The review covers application code, tests, resource wiring, and packaging;
vendored third-party bundles were exercised through the application rather than
audited line by line. Windows and macOS were not tested.

## Architecture and maintainability refactor — 2026-11-02

This follow-up implements the requested structural cleanup on top of the reviewed
working tree. Existing staged work was preserved; no commit or push was made.
The original review above describes the state before this refactor.

| Area | Result |
| --- | --- |
| Desktop composition | `desktop.py` now contains application startup. Window lifetime, WebEngine policy, bridge commands, worker execution, scheduling and window ownership have dedicated modules under `reader/ui/`. A window factory removes the runtime circular dependency. |
| Background work | `DocumentJobs` owns serial scheduling and preview coalescing. `PreviewRequest` describes a captured render request. Closed documents and stopped windows reject late results; stopped windows reject new work. Reopened files receive a fresh ID while any previous preview, formatting or PDF job still owns the old one. |
| Transfers | `TabTransfer` replaces unstructured state dictionaries. Acknowledgments before delivery cannot remove the original buffer. Transfer rollback uses the same session-release path as document closure. |
| Preferences and storage | Preferences are validated independently of Qt on both reading and writing. Malformed values are repaired individually. Library lookup uses indexed queries for the requested document and its annotations instead of reading the full library. |
| Browser responsibilities | Search, outline, file tabs, source editing and native window gestures are independent factory modules. Application commands use an explicit dispatch map. |
| PDF views | Main and extra panes share `pdf-pages.js`, including observer disposal and stale-response checks. The first page is requested eagerly so its image does not depend on visibility callbacks; later pages remain lazy. |
| Readability and tools | First-party Python, JavaScript, HTML and CSS are consistently formatted. Ruff, ESLint and Prettier configurations are checked in with pinned development dependencies. Vendored libraries and fonts were left unchanged. |
| Project knowledge | `ARCHITECTURE.md` records ownership, dependency direction, asynchronous invariants, persistence and extension guidance. README paths and commands match the new structure. `scripts/smoke.py` runs desktop checks sequentially with timeouts and retained logs. |

Validation of the refactor:

- 63 Python unit tests pass. New tests cover preference repair, preview coalescing,
  failure recovery, loading reservations, late job results, shutdown, transfer
  rollback, early acknowledgments, reopened document identity and targeted library
  lookup.
- All six Node test files pass, including PDF lifecycle checks for eager initial
  loading, hidden panes, observer disposal, stale snapshots and render errors.
- All 12 source desktop checks pass in their latest runs. The full initial run
  passed 10/12: desktop startup exceeded its wait once, and zoom expected an exact
  HTML text node without formatting whitespace. The zoom assertion now trims
  whitespace while still checking both the label and actual zoom. Desktop and
  zoom passed their focused reruns. Startup timeout diagnostics now include native
  queue/session state, font status and browser visibility; no independent root
  cause for that one startup timeout was established.
- The intermittent first-PDF-image timeout also occurred before eager first-page
  loading was added. The formats check passed twice consecutively after that
  change. This confirms the new request policy and the tested scenarios; it is
  not a claim that every possible compositor/timing issue has been eliminated.
- Ruff lint/format, ESLint, Prettier, Python 3.10 syntax parsing, HTML ID/resource
  wiring, dependency consistency, CLI version and whitespace checks pass.
- Comparing the Python service ASTs to the pre-refactor snapshot confirms that
  changes outside the desktop split, preferences and scheduling are limited to
  the intended library queries and an explicit HTML paragraph helper; other
  existing service changes are formatting/import cleanup.

Logs and the consolidated latest source results are in `artifacts/refactor/`.
Failed initial runs are retained alongside the successful focused reruns.

Fresh one-directory, portable and Debian builds completed successfully. The new
portable executable passed the bundle smoke check, and the new Debian package
passed its integration check, including persistence, API execution, Word export,
PDF rendering/editing/saving and Wayland/X11 identity. Both SHA-256 files verify.
Outputs are `dist/Khana` and `dist/khana_0.5.4-1_amd64.deb`; package logs are in
`artifacts/refactor/packages/`. The consolidated report is
`artifacts/refactor/results.json`. No package was installed or published.
