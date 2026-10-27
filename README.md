# Khana

A local desktop reader and editor for mixed Persian and English documents. Open Markdown, HTML, Word, PDF, JSON, YAML, logs, configuration files, and XML. Edit supported content with a synchronized preview. Each prose paragraph is displayed in its own direction. The application interface is English; document content keeps its original language.

## Installation

| Method | Requirements | Desktop integration |
| --- | --- | --- |
| [Ubuntu installer](#install-on-ubuntu) | Ubuntu 26.04, x86_64 / amd64 | Application search, logo, dock pinning, and Open With |
| [Run from source](#run-from-source) | Python 3.10–3.15 and a graphical desktop | Run from a terminal or IDE |
| [Portable executable](#portable-desktop-app) | Ubuntu 26.04, x86_64 / amd64 | Run the executable directly |

The verified environment is Ubuntu 26.04 x86_64 with Python 3.14. Windows source commands are provided below, but a Windows build has not been tested or published. The Linux binaries are not intended for Windows, macOS, ARM, or older Ubuntu versions.

**Downloads:** check [GitHub Releases](https://github.com/mehmed18q/markdown_tool/releases) for attached installers. If there is no `.deb` asset, [run from source](#run-from-source) or [build the installer](#build-the-ubuntu-installer). The `dist/`, `build/`, and `.venv/` directories are generated locally and are not included when cloning the repository or downloading its source ZIP.

## Install on Ubuntu

The `.deb` package includes Python, Qt WebEngine, the PDF engine, fonts, and the offline diagram renderer. Its LibreOffice Writer dependency provides `.doc` / `.docx` import and export; `apt install` installs it when needed. You do not need to clone the project or install Python separately.

1. Open [Releases](https://github.com/mehmed18q/markdown_tool/releases) and expand the release's **Assets**.
2. Download the `.deb` file and its matching `.deb.sha256` file. For version 0.5.4 these are `khana_0.5.4-1_amd64.deb` and `khana_0.5.4-1_amd64.deb.sha256`.
3. Open a terminal in the download folder and run the following commands. Use the downloaded filenames if the version differs.

```bash
sha256sum -c khana_0.5.4-1_amd64.deb.sha256
sudo apt install ./khana_0.5.4-1_amd64.deb
```

The checksum command should report **OK**. Installation asks for your Ubuntu administrator password. You can also open the `.deb` with your system's package installer.

After installation, close any old portable Khana window, search for **Khana** in **Show Applications**, and launch it. Right-click its icon to choose **Pin to Dash** / **Add to Favorites**. You can also start it from a terminal:

```bash
khana
khana /path/to/document.md /path/to/page.html
```

To upgrade, download the newer `.deb` and install it with the same `sudo apt install ./filename.deb` command. To uninstall:

```bash
sudo apt remove khana
```

Your documents and preferences are retained on removal. Installed and portable builds store preferences in `~/.config/Khana/Khana/settings.ini` (or beneath `XDG_CONFIG_HOME`). The package does not change your default HTML/Markdown application.

## Run from source

An internet connection is needed to download dependencies; reading and editing work offline afterward. Run the following commands as your normal desktop user.

### Ubuntu

On Ubuntu 26.04, install Python, Git, and the desktop libraries needed by Qt:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip libreoffice-writer \
  libegl1 libgl1 libnss3 libasound2t64 \
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-render-util0 libxcb-xkb1 libxkbcommon-x11-0
```

Then clone the repository and create a virtual environment:

```bash
git clone https://github.com/mehmed18q/markdown_tool.git
cd markdown_tool
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Other Linux distributions need their corresponding Python and Qt runtime packages. The application requires a graphical desktop session.

### Windows (source only)

Install a supported 64-bit Python version and Git first. In PowerShell:

```powershell
git clone https://github.com/mehmed18q/markdown_tool.git
cd markdown_tool
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

No activation script or PowerShell execution-policy change is needed because these commands call the virtual environment's Python directly. If you do not use Git, choose **Code → Download ZIP** on the [repository page](https://github.com/mehmed18q/markdown_tool), extract it, open a terminal in the extracted folder, and start with the virtual-environment step.

### First launch

Khana starts fullscreen with a sample document. Press **F11**, or click the F11 button, to return to a regular window. The **Minimize** button in the top bar sends the window to the taskbar/dock.

Drag the filename, empty space in the top bar, or the Khana logo to move the window to another monitor. Dragging from fullscreen restores a regular window first; press **F11** on the destination monitor to fill it again. Double-click the same header areas to toggle fullscreen. Header buttons keep their normal actions.

Click **Open file** to read an existing document or **New document** to start writing. Use **Edit & Preview** for editing and live preview; **Save** and **Save As…** write your changes to disk.

Use **Ctrl + mouse wheel** over the document to zoom only the preview. The **Preview zoom** buttons and **Ctrl++ / Ctrl+−** adjust magnification from 50% to 300%; click **Reset** or press **Ctrl+0** to reset to 100%. Text, images, tables, diagrams, and PDF pages scale together. The sidebar, toolbars, and source editor keep their size. The zoom level is remembered across restarts, and editor/preview scroll synchronization remains available.

You can pass files at startup when running from source:

```bash
.venv/bin/python main.py examples/welcome.md examples/mixed-content.html
```

For PyCharm or another IDE, select the project's `.venv` interpreter and run `main.py`. Source runs store preferences in the project's `.local/settings.ini`.

## Build the Ubuntu installer

Build on **Ubuntu 26.04 x86_64**. First follow the [Ubuntu source setup](#ubuntu) through dependency installation. From the cloned project folder:

```bash
sudo apt install curl dpkg desktop-file-utils
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python scripts/build_deb.py
sudo apt install ./dist/khana_0.5.4-1_amd64.deb
```

The build produces `dist/khana_0.5.4-1_amd64.deb` and its `.deb.sha256` checksum. Build as your normal user; only the final installation command needs administrator access.

The installer registers `/usr/bin/khana`, `/usr/share/applications/io.khana.Khana.desktop`, and the SVG/PNG logo under the system icon theme. Its runtime is installed in `/opt/khana`. The application ID, desktop entry, and icon name match so the desktop displays **Khana** and associates its running window with the launcher.

The build downloads eight small X11 libraries from the Ubuntu archive, verifies their pinned hashes, and stages them in `build/linux-libs` without installing them into the build machine's system directories. Subsequent builds reuse the downloads. PyInstaller settings are in `packaging/khana.spec`; third-party license notices are included with the runtime.

## Portable desktop app

If a `Khana` executable is attached to [Releases](https://github.com/mehmed18q/markdown_tool/releases), download it with `SHA256SUMS`. From the download folder:

```bash
sha256sum -c SHA256SUMS
chmod +x Khana
./Khana
```

To build it yourself, complete the build prerequisites above and run:

```bash
.venv/bin/python scripts/build_linux.py
./dist/Khana
```

The single executable includes Python and the app's resources and can be moved to another folder. Startup may take a few seconds while its runtime unpacks. It does not register an installed application: use the `.deb` for application search and dock pinning. The optional generated `io.khana.Khana.desktop` launcher refers to the build folder and must be updated if moved.

## Troubleshooting installation

- **No installer in Releases / no `dist` folder:** use the source setup or build the installer locally. GitHub's **Source code** archives contain source files, not a built application.
- **`python3 -m venv` fails on Ubuntu:** install `python3-venv`, then rerun the environment-creation command.
- **Qt reports a missing `xcb` plugin dependency:** install the Qt runtime libraries listed in the Ubuntu source instructions. Run from a graphical desktop rather than a terminal-only server session.
- **The dock shows `io.khana.Khana`, has no icon, or cannot pin the app:** install the `.deb`, close the portable/source window, and start **Khana** from the application list.
- **The `.deb` reports a `libc6` version or architecture mismatch:** it targets Ubuntu 26.04 amd64. Use an environment compatible with that build, or try the source setup with dependencies supported by your system.
- **The whole screen is occupied:** press **F11** to leave fullscreen.

## Publishing downloads (maintainers)

Build outputs are excluded by `.gitignore`; pushing the source does not publish an installer. After building and verifying a version, create a [GitHub Release](https://github.com/mehmed18q/markdown_tool/releases) for that version and attach:

| Asset | Purpose |
| --- | --- |
| `dist/khana_0.5.4-1_amd64.deb` | Ubuntu installer |
| `dist/khana_0.5.4-1_amd64.deb.sha256` | Installer checksum |
| `dist/Khana` (optional) | Portable Linux executable |
| `dist/SHA256SUMS` (with the portable executable) | Portable executable checksum |

These names describe version 0.5.4. Update versioned examples when publishing a newer package. Build and test each asset from the same release source before uploading it.

## Reading

- Open `.md`, `.markdown`, `.mdown`, `.mkd`, `.txt`, `.html`, `.htm`, `.docx`, `.doc`, `.pdf`, `.json`, `.yaml`, `.yml`, `.log`, `.conf`, `.cfg`, `.ini`, or `.xml` files with **Open file**, drag and drop, or the command line.
- Keep several documents open and use **ON THIS PAGE** to jump to headings.
- **Smart** detects each paragraph, heading, list item, and table cell independently. A Persian sentence beginning with an English product name remains right to left. Primarily English paragraphs remain left to right.
- Code blocks remain left to right. English phrases, inline code, paths, and URLs are isolated from surrounding Persian text. English phrases spanning emphasis or links are kept together.
- **RTL** and **LTR** override the document direction. Hover beside a paragraph or heading to cycle that individual block through RTL, LTR, and automatic direction. These overrides last while the file remains open and reset when it is reloaded.
- Search highlights text across inline formatting. Use Enter / Shift+Enter or the arrow buttons to move through matches. Up to 2,000 matches are highlighted.
- Adjust font size, line spacing, page width, light/dark theme, or focus mode. Preferences stay on your device: installed/portable builds use `~/.config/Khana/Khana/settings.ini`, while source runs use `.local/settings.ini` in the project.
- **Reload** reads a file again after changes in another editor. If you have local edits, choose Save, Discard, or Cancel before reloading.

## Library, reading marks, and notes

- Opened files stay in **LIBRARY** after closing their tabs or restarting Khana. The last open saved documents reopen at startup. Missing files stay listed as **File not found** so their annotations are retained.
- Use **Star document**, or the star beside a library entry, to keep favorites in the **Starred** filter. Click an entry to reopen it. Close its tab first to remove it from the library; removal also clears its stars, marks, and notes, but keeps the source file.
- Each document supports multiple named marks and notes. Hover beside a paragraph and choose **Add a mark here** or **Add a note here**. You can also select text in the reading view and click **Add mark** (Ctrl+M) or **Add note** (Ctrl+Shift+M). Without a selection, these toolbar actions use the top visible reading block.
- **Marks & Notes** lists each saved location and note. Click its name to jump there; use **Edit** to rename a mark or update a note, and **Delete** to remove either. Inline badges identify annotated blocks in the document.
- **Resume** returns to the most recently added or visited mark/note, also used when reopening the file. Marks match text and neighboring blocks, so inserting content above an unchanged paragraph keeps its location. If the original text has changed or disappeared, navigation uses an approximate location and shows a warning.
- Save a new document and any pending source changes before adding annotations. Notes and marks save immediately and independently of the document's **Save** button; the source file is unchanged. **Save As…** to a new path copies its stars and annotations, and the two documents can then be annotated independently.

Reading information is local to this device, in `library.sqlite3` beside `settings.ini`: installed/portable builds use `~/.config/Khana/Khana/`, and source runs use the project's `.local/` folder. Back up that database with the app closed to preserve the library. Moving a source file outside Khana does not automatically update its library path. Unsaved drafts are not restored after closing the app.

## Create, edit, and save

- Select **MD**, **HTML**, **Word**, **JSON**, **YAML**, **LOG**, **CONF**, or **XML** beside **New document**, then click the button (or press Ctrl+N) to create a draft.
- Select **Edit & Preview** (Ctrl+E) to edit the original source beside a live preview. The preview updates after a brief pause in typing. Use **Read** to return to the full reading layout.
- **Sync scroll** is enabled by default: scrolling the editor moves the preview to corresponding source lines, and scrolling the preview moves the editor back to those lines. Wrapped source lines and rendered block heights are taken into account. Live updates follow the editing position. Uncheck **Sync scroll** in the editor footer for independent scrolling; this preference survives restarts. HTML with several elements on one source line is mapped at that line's granularity.
- The formatting and image toolbar appears only for **Markdown**, **HTML**, and **Word**. JSON, YAML, LOG, CONF, XML, and PDF do not display text-formatting controls; formatting shortcuts do not insert markup into data files.
- **Image** opens a local file picker. Markdown and HTML use an absolute `file:///…` URL, including files outside the document folder. Images can be inserted before saving a draft. Moving or deleting that image later breaks the reference; Word embeds images when saved.
- Each document keeps its own source buffer and undo history while switching tabs or reading modes. Standard Ctrl+Z / Ctrl+Shift+Z editing shortcuts work in the source field.
- The editor has independent **Auto / LTR / RTL** direction controls. The reading toolbar controls the preview direction.
- The source toolbar provides **Bold**, **Italic**, **Strikethrough**, **H1–H3**, **Link**, **Inline code**, **Code block**, **Quote**, **Bulleted list**, **Numbered list**, and **Horizontal rule**. Select source text and choose a button; without a selection, inline tools insert a selected placeholder. Headings and Markdown lists act on the selected/current lines.
- Formatting inserts Markdown syntax in Markdown documents and HTML tags in HTML documents. The result appears in the preview. Toolbar operations are undoable with Ctrl+Z. The link dialog supports a label and an HTTP(S), mailto, heading, or relative document destination.
- **Save** (Ctrl+S) updates the current file. A new draft opens a filename dialog; a missing extension is added automatically. Sample documents also use a filename dialog.
- **Save As…** (Ctrl+Shift+S) writes to a new name or location and makes that the active file. Later saves update the new path. Source format is preserved: this is not Markdown-to-HTML export.
- An amber dot and **Unsaved changes** identify modified documents. Closing a modified file, reloading it, or closing the application offers **Save / Discard / Cancel**. Canceling a filename dialog keeps the draft open.
- Opening an already open file activates its existing buffer. Save As cannot overwrite a file that is open in another tab.
- Saving writes the original source, including HTML styles and scripts; sanitization applies only to the preview. Existing UTF-8 / UTF-16 encoding, byte-order marks, and newline style are retained. New documents use UTF-8.
- Files are written through a temporary file and an atomic commit. Save errors leave edits open. If a file changed on disk, replacement requires confirmation. Drafts live in memory until saved; there is no automatic recovery after a crash.

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Open files |
| Ctrl+N | New document in the selected format |
| Ctrl+E | Toggle Edit & Preview |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+W | Close the current document |
| Ctrl+B | Toggle bold in the source editor |
| Ctrl+I | Toggle italic in the source editor |
| Ctrl+K | Insert a link |
| Ctrl+Shift+X | Toggle strikethrough |
| Ctrl+` | Inline code |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo source editing |
| Ctrl+F | Find in the current document |
| Ctrl+R | Reload from disk |
| Ctrl+M | Add a reading mark |
| Ctrl+Shift+M | Add a note |
| Ctrl+Shift+F | Toggle focus mode |
| F11 | Toggle fullscreen |
| Ctrl++ / Ctrl+− | Zoom the document preview in / out |
| Ctrl+0 | Reset preview zoom to 100% |
| Ctrl+Shift+I | Format JSON, YAML or XML source in editing mode |
| Escape | Close appearance/search, or leave focus mode |

## Tables and flowcharts

In **Edit & Preview**, place the caret in the source and choose **Table** or **Flowchart**. Insertion replaces selected source text, if any, and supports Ctrl+Z / Ctrl+Shift+Z.

- **Table** opens an editable grid with a header row and 1–50 data rows, with up to 12 columns. Fill the cells or paste tab-separated cells from a spreadsheet. Pasting expands the grid within those limits; oversized pastes show an error. Cells support Persian and English. Markdown cells may use inline Markdown formatting; HTML cell contents are escaped as literal text.
- **Flowchart** lets you add and remove steps, choose **Process**, **Start / End**, **Decision**, or **Input / Output** shapes, and connect them with optional labels. Branches and loops are supported. Choose top-to-bottom, bottom-to-top, left-to-right, or right-to-left layout. A chart can have up to 30 steps and 60 connections in the builder.
- Diagrams render offline in both reading mode and live preview, with mixed-language labels, light/dark themes, zoom, **Fit**, **Copy source**, and an expandable **Mermaid source** section. Invalid diagrams show an error beside their source while the rest of the document stays readable.
- The builders insert editable source. To change an existing table or flowchart, edit that source in **Edit & Preview**. The forms currently create new items; they do not reopen existing ones for visual editing.

Markdown diagrams use standard Mermaid fences:

````markdown
```mermaid
flowchart TD
  accTitle: Order process
  A(["شروع Start"]) --> B{"آماده است؟"}
  B -->|"بله Yes"| C(["پایان End"])
  B -->|"خیر No"| A
```
````

HTML diagrams use `<pre><code class="language-mermaid">…</code></pre>` with HTML-escaped Mermaid source. Saving preserves this source; displaying it in another application requires Mermaid support. This is not a standalone HTML/SVG export.

Open [examples/tables-and-flowcharts.md](examples/tables-and-flowcharts.md) for a table, a branching order process, and a right-to-left release pipeline. Rendering limits are 50,000 source characters and 200 edges per diagram. Diagrams run in strict mode; graph links and embedded HTML/images are disabled and application security/theme settings cannot be overridden by document directives.

## HTML and local files

HTML is displayed in a consistent reading layout: headings, paragraphs, lists, links, tables, images, code, and disclosure sections. Scripts, forms, embedded pages, and the original page's CSS are removed. Existing HTML `dir="rtl"` / `dir="ltr"` hints are honored in Smart mode.

Reading and editing need no server or internet connection after installation. Documents are not uploaded. The optional Swagger **Execute** action sends the selected HTTP request, including its parameters, body and applicable authorization, to the selected API server. Images can use relative paths, absolute system paths, or local `file:///…` URLs; embedded Word images are supported too. Remote images are replaced by placeholders. External links open in your default browser only when clicked. Relative supported-document links inside the document's folder open in Khana.

Text files must use UTF-8 (with or without BOM) or UTF-16 with BOM. The current file-size limit is 5 MB, including Word and PDF files. Raw HTML embedded inside Markdown is shown as text. Smart direction is a heuristic; use the manual direction controls for ambiguous sentences.

## Word, PDF, and structured text

| Format | Reading and editing |
| --- | --- |
| JSON, YAML | OpenAPI / Swagger definitions open as offline Swagger UI documentation. Other files show literal source with syntax colors and line numbers. Incomplete syntax remains visible while typing. |
| XML | Literal source with syntax colors and line numbers; edit and save without reformatting or executing it. |
| LOG, CONF (`.conf`, `.cfg`, `.ini`) | Literal lines, preserved whitespace, search, marks, notes, and source editing. Configuration syntax is highlighted as INI; logs remain plain text. |
| Word (`.docx`, `.doc`) | Import text, headings, common character styles, tables, and images into an HTML editing source. Formatting buttons insert HTML; saving exports back to Word through LibreOffice Writer. |
| PDF | Original pages rendered on demand, with simple text-region replacement. Image-only pages and complex text regions remain read-only. |

Word requires LibreOffice Writer (`libreoffice` or `soffice` on PATH for source/portable runs, including Windows). Each conversion uses a temporary isolated profile. Word editing uses a simplified reading layout; saving edited content may change advanced Word features such as page layout, fields, headers, tracked changes, and complex styles. Use **Save As…** when keeping the original layout is important.

For **JSON, YAML and XML**, choose **Edit & Preview**, then **Format document** (or **Ctrl+Shift+I**). This applies consistent two-space indentation and spacing without sorting keys. JSON numbers and strings retain their original spellings; YAML keeps comments, quotes, anchors, tags, document separators, and existing inline/block styles. XML keeps comments and mixed text and respects `xml:space="preserve"`; XML containing a DTD is left unchanged. Invalid input reports an error without changing the source. Formatting is one undoable edit (**Ctrl+Z**); use **Save** to write it to disk. This button is separate from the prose styling toolbar and appears only for supported structured formats.

### Swagger / OpenAPI preview

Open a `.json`, `.yaml`, or `.yml` definition with a root `swagger: "2.0"` or `openapi: 3.0.x / 3.1.x / 3.2.x`. Khana automatically displays **Swagger UI** with expandable endpoints, parameters, responses, and schemas. Use **Source** in the preview toolbar to see the original text, or **Edit & Preview** to edit it with a live API preview. The original source is only written when you save. Invalid or unsupported definitions remain visible as source.

The preview includes endpoint navigation, a tag/path filter, Persian/English descriptions, preview zoom, synchronized source scrolling, and marks/notes attached to API operations. Swagger UI is bundled locally. Online validation and external `$ref` loading remain disabled; internal `#/...` references work. For definitions split across files, open a bundled specification to see all models.

To call an API, expand an endpoint, click **Try it out**, fill in its parameters/body, and click **Execute**. The response includes its status, headers, body and elapsed time. Opening or editing a definition does not send API requests. HTTP requests use the native desktop client, so browser CORS headers are not required.

**Authorize** supports the security schemes defined in the document: **Bearer**, **Basic**, and **API Key** in a header, query or cookie. Public operations need no authorization. For **OAuth2**, paste an existing access token; browser sign-in, token acquisition and automatic refresh are not implemented. Logout removes the selected credentials. Authorization is held in memory for each open document, survives preview changes, and is discarded when that document or the app is closed; it is never written to the source, library or settings.

Under **Request settings**, optionally set a full **Server URL override**, including any base path such as `/v1`. This is useful for relative server URLs and local test servers. Applying a different base URL clears authorization. **Cancel requests** cancels pending requests for the current document; switching previews/documents also cancels pending requests. Cancellation cannot undo a request already received by the server. Each request has a 30-second timeout and a 10 MB request/response limit. HTTPS certificate verification remains enabled, cookies are not shared or saved automatically, and redirects are displayed without automatically following them.

For a PDF, hover over an editable text region and click **Edit text** (or double-click the region). Enter replacement text, choose **Apply**, review the page, then **Save** or **Save As…**. Text is replaced within its existing region; longer replacements may shrink to fit, and replacements that do not fit are rejected. Replacement fonts may differ from the original. Overlapping/rotated regions and PDFs without editable text are for reading only. Password-protected PDFs require an unlocked copy. No OCR or general page-layout editor is included. PDF page text can still be searched and annotated.

## Project layout

| Path | Responsibility |
| --- | --- |
| `main.py` | Application entry point |
| `reader/desktop.py` | Qt window, file dialogs, document sessions, preview workers, save/close prompts |
| `reader/documents.py` | Document loading, Markdown rendering, HTML sanitization |
| `reader/editing.py` | Source buffers, encoding preservation, conflict detection, atomic writes |
| `reader/source_formatting.py` | JSON, YAML and XML source beautification |
| `reader/openapi_documents.py`, `reader/web/openapi-ui.js` | Safe API definition detection and offline Swagger UI preview |
| `reader/api_requests.py`, `reader/web/api-requests.js` | Native HTTP transport for explicit Swagger Execute actions |
| `reader/library.py` | Persistent document library, stars, reading marks, notes, and session restoration |
| `reader/word_documents.py`, `reader/pdf_documents.py` | Word conversion, PDF pages, and simple PDF text replacement |
| `reader/web/annotations.js`, `reader/web/library-ui.js`, `reader/web/library.css` | Text anchors and library/annotation controls |
| `reader/web/bidi.js` | Direction detection and inline isolation |
| `reader/web/app.js` | Reading interface and document state |
| `reader/web/preview-zoom.js` | Preview magnification, wheel/keyboard controls, and reading-position anchoring |
| `reader/web/scroll-sync.js`, `reader/web/pdf-ui.js`, `reader/web/formats.css` | Bidirectional scroll mapping, PDF controls, and source-line presentation |
| `reader/web/formatting.js` | Selection transformations for formatting and links |
| `reader/web/insertions.js`, `reader/web/builders.js` | Table/flowchart serialization and builder dialogs |
| `reader/web/diagrams.js` | Offline diagram rendering, direction, themes, and zoom |
| `reader/web/styles.css`, `reader/web/editor.css` | Themes, typography, and reading/editor layouts |
| `reader/web/builders.css` | Builder forms and diagram presentation |
| `examples/` | Persian/English Markdown and HTML samples |

The renderer is shared by the reading view and live preview. Source buffers stay separate from rendered HTML so saving never replaces the original source with the sanitized preview.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/bidi.test.cjs
node --test tests/formatting.test.cjs
node --test tests/insertions.test.cjs
node --test tests/annotations.test.cjs
node --test tests/scroll-sync.test.cjs
.venv/bin/python tests/desktop_smoke.py
.venv/bin/python tests/zoom_smoke.py
.venv/bin/python tests/beautify_smoke.py
.venv/bin/python tests/openapi_smoke.py
.venv/bin/python tests/api_requests_smoke.py
.venv/bin/python tests/api_transport_smoke.py
.venv/bin/python tests/editor_smoke.py
.venv/bin/python tests/builders_smoke.py
.venv/bin/python tests/library_smoke.py
.venv/bin/python tests/formats_smoke.py
```

The smoke checks require a graphical desktop and exercise the actual Qt/WebEngine window, reading, editing, live preview, saving, save-as, external changes, save/discard/cancel behavior, table/flowchart builders, diagram rendering, annotation persistence, both scroll directions, Word/PDF editing, image insertion, and Swagger / OpenAPI previews. The formats check also needs LibreOffice Writer. They use temporary files and save screenshots in `artifacts/`. Node is only needed for JavaScript unit tests, not to run the app.

After building, verify the packaged application on a graphical desktop:

```bash
.venv/bin/python tests/bundle_smoke.py dist/Khana
.venv/bin/python tests/deb_smoke.py
```

The first command requires a portable build; the second requires the `.deb`. The Debian check also uses Ubuntu's system Python with PyGObject/GTK 4, plus `xprop` for X11 checks. These checks use temporary documents and configuration, and test the package without installing it into your system. A local DevTools endpoint is enabled only in the test process.

The bundled Noto Sans Arabic font's license is included in `reader/web/fonts/LICENSE.txt`. PySide6/Qt and the other dependencies retain their respective upstream licenses.

Mermaid 11.12.2 is bundled locally under the MIT license; see [vendor notes](reader/web/vendor/README.md) and `reader/web/vendor/MERMAID-LICENSE.txt`. No CDN access is used at runtime.

PDF page rendering and text replacement use PyMuPDF; its license is included in the packaged third-party notices. The implementation uses its [text insertion and redaction APIs](https://pymupdf.readthedocs.io/en/latest/page.html), with image and vector removal disabled for text replacements.
