"""Document loading and rendering, independent of the desktop UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
import nh3
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

MAX_FILE_BYTES = 5 * 1024 * 1024
FORMAT_EXTENSIONS = {
    "Markdown": (".md", ".markdown", ".mdown", ".mkd", ".txt"),
    "HTML": (".html", ".htm"), "JSON": (".json",), "YAML": (".yaml", ".yml"),
    "LOG": (".log",), "CONF": (".conf", ".cfg", ".ini"), "XML": (".xml",),
    "Word": (".docx", ".doc"), "PDF": (".pdf",),
}
EXTENSIONS = {extension for extensions in FORMAT_EXTENSIONS.values() for extension in extensions}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}


def format_for_path(path: Path) -> str:
    for name, extensions in FORMAT_EXTENSIONS.items():
        if path.suffix.lower() in extensions:
            return name
    raise ValueError("Choose a supported document or text file (Markdown, HTML, Word, PDF, JSON, YAML, LOG, CONF, XML).")


def file_filter(document_format: str) -> str:
    return f"{document_format} ({' '.join('*' + ext for ext in FORMAT_EXTENSIONS[document_format])})"


def local_image(raw: str, base_directory: Path | None) -> str | None:
    parsed = urlparse(raw)
    if parsed.scheme not in {'', 'file'} or parsed.netloc not in {'', 'localhost'} or not parsed.path:
        return None
    path = Path(unquote(parsed.path))
    if not path.is_absolute():
        if base_directory is None: return None
        path = base_directory / path
    path = path.resolve()
    return path.as_uri() if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file() else None


@dataclass
class Document:
    id: str
    name: str
    path: str
    html: str
    headings: list[dict]
    words: int
    size: int
    encoding: str
    sample: bool = False
    format: str = "Markdown"
    source: str = ""
    codec: str = "utf-8"
    bom: str = ""
    newline: str = "\n"
    fingerprint: str = ""
    api: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _highlight(code: str, language: str, _attrs: str = "") -> str:
    if language == "mermaid" or len(code) > 100_000:
        return escape(code)
    try:
        lexer = get_lexer_by_name(language) if language else None
    except ClassNotFound:
        lexer = None
    return highlight(code, lexer, HtmlFormatter(nowrap=True)) if lexer else escape(code)


def render_markdown(source: str, base_directory: Path | None = None) -> tuple[str, list[dict]]:
    """Keep raw HTML inert and resolve only local images inside the document folder."""
    parser = MarkdownIt("commonmark", {"html": False, "highlight": _highlight})
    validate_link = parser.validateLink
    parser.validateLink = lambda url: bool(local_image(url, base_directory)) if urlparse(url).scheme == 'file' else validate_link(url)
    parser.enable(["table", "strikethrough"])
    original_image = parser.renderer.rules["image"]

    def image_rule(tokens, index, options, env):
        token = tokens[index]
        raw = token.attrGet("src") or ""
        resolved = local_image(raw, base_directory)
        if resolved:
            token.attrSet("src", resolved)
            token.attrSet("loading", "lazy")
            return original_image(tokens, index, options, env)
        label = escape(token.content or "Image")
        return f'<span class="image-placeholder" role="img" aria-label="{label}">▧ {label} <small>Image unavailable</small></span>'

    parser.renderer.rules["image"] = image_rule
    # Fences/code blocks have a custom renderer, which does not emit token attrs.
    for kind in ("fence", "code_block"):
        original_rule = parser.renderer.rules[kind]
        def mapped_code(tokens, index, options, env, rule=original_rule):
            rendered = rule(tokens, index, options, env)
            start, end = tokens[index].map
            return rendered.replace('<pre>', f'<pre data-source-line="{start}" data-source-end="{end}">', 1)
        parser.renderer.rules[kind] = mapped_code
    tokens = parser.parse(source)
    headings = []
    used_ids: set[str] = set()
    for index, token in enumerate(tokens):
        if token.map and token.block and token.type not in {"inline", "fence", "code_block"}:
            token.attrSet("data-source-line", str(token.map[0]))
            token.attrSet("data-source-end", str(token.map[1]))
        if token.type != "heading_open":
            continue
        inline = tokens[index + 1]
        title = "".join(t.content for t in inline.children or [] if t.type in {"text", "code_inline"})
        slug = re.sub(r"[^\w\-\s\u200c]", "", title.lower(), flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug.strip()) or "section"
        unique, count = slug, 0
        while unique in used_ids:
            count += 1
            unique = f"{slug}-{count}"
        used_ids.add(unique)
        token.attrSet("id", f"doc-heading-{unique}")
        headings.append({"id": f"doc-heading-{unique}", "title": title, "level": int(token.tag[1])})
    for token in tokens:
        for child in token.children or []:
            href = child.attrGet("href") if child.type == "link_open" else None
            if href and href.startswith("#"):
                child.attrSet("href", "#doc-heading-" + href[1:])
    return parser.renderer.render(tokens, parser.options, {}), headings


def render_html(source: str, base_directory: Path | None = None) -> tuple[str, list[dict]]:
    """Turn HTML documents into inert reading content, without page CSS or scripts."""
    original = BeautifulSoup(source, "html.parser")
    # Replace document-provided metadata with parser positions before sanitizing.
    for element in original.find_all(True):
        element.attrs.pop('data-source-end', None)
        element['data-source-line'] = str(max(0, (element.sourceline or 1) - 1))
    root_direction = None
    for container in (original.body, original.html):
        if container and container.get("dir") in {"rtl", "ltr"}:
            root_direction = container["dir"]
            break
    tags = set("p div section article main aside header footer span h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li dl dt dd table thead tbody tfoot tr th td caption colgroup col a img hr br strong em b i u s del sub sup small abbr bdi details summary kbd samp mark figure figcaption".split())
    cleaned = nh3.clean(
        str(original), tags=tags,
        clean_content_tags={"head", "title", "script", "style", "iframe", "object", "embed", "template", "svg", "math", "form", "noscript"},
        attributes={"*": {"id", "dir", "title", "data-source-line"}, "a": {"href"}, "img": {"src", "alt"}, "th": {"colspan", "rowspan"}, "td": {"colspan", "rowspan"}, "ol": {"start"}},
        url_schemes={"http", "https", "mailto", "file", "data"},
        allowed_classes={"code": {"language-mermaid"}},
    )
    soup = BeautifulSoup(cleaned, "html.parser")
    used_ids: set[str] = set()
    links: dict[str, str] = {}
    headings = []
    for element in soup.find_all(True):
        if element.get("dir") not in {"ltr", "rtl", "auto", None}:
            del element["dir"]
        is_heading = element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
        original = element.get("id", "")
        if not original and not is_heading:
            continue
        title = element.get_text()
        slug = original or re.sub(r"[^\w\-\s\u200c]", "", title.lower(), flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug.strip()) or "section"
        unique, number = f"doc-heading-{slug}", 0
        while unique in used_ids:
            number += 1
            unique = f"doc-heading-{slug}-{number}"
        used_ids.add(unique)
        element["id"] = unique
        links.setdefault(original or slug, unique)
        if is_heading:
            headings.append({"id": unique, "title": title, "level": int(element.name[1])})
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("#"):
            fragment = unquote(href[1:])
            link["href"] = "#" + links.get(fragment, "doc-heading-" + fragment)
    for image in soup.find_all("img"):
        raw = image.get('src', '')
        resolved = local_image(raw, base_directory)
        embedded = re.fullmatch(r'data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+', raw)
        if resolved or embedded:
            image['src'] = resolved or raw
            image['loading'] = 'lazy'
            continue
        placeholder = soup.new_tag("span", attrs={"class": "image-placeholder", "role": "img"})
        placeholder.string = f"▧ {image.get('alt', 'Image')} — Image unavailable"
        image.replace_with(placeholder)
    # Normalize bare body text and div-based prose into paragraphs so the same
    # per-paragraph direction engine applies to exported HTML and Markdown.
    block_names = {"p", "div", "section", "article", "main", "aside", "header", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "ul", "ol", "li", "table", "dl", "figure", "details", "hr"}
    for container in [soup, *soup.find_all(["div", "section", "article", "main", "aside", "header", "footer"])]:
        run = []
        def wrap_run():
            if run and any(str(item).strip() for item in run):
                paragraph = soup.new_tag("p")
                line = next((item.get('data-source-line') for item in run if getattr(item, 'attrs', None) and item.get('data-source-line')), None)
                paragraph['data-source-line'] = line or container.get('data-source-line', '0')
                run[0].insert_before(paragraph)
                for item in run:
                    paragraph.append(item.extract())
            run.clear()
        for child in list(container.children):
            if child.name in block_names:
                wrap_run()
            else:
                run.append(child)
        wrap_run()
    result = str(soup)
    if root_direction:
        result = f'<div dir="{root_direction}">{result}</div>'
    return result, headings


def render_code_document(source: str, document_format: str) -> tuple[str, list[dict]]:
    """Show source literally, including incomplete/invalid data during editing."""
    language = {"JSON": "json", "YAML": "yaml", "LOG": "text", "CONF": "ini", "XML": "xml"}[document_format]
    lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
    rendered = highlight(source, lexer, HtmlFormatter(nowrap=True)) if len(source) <= 100_000 else escape(source)
    # HtmlFormatter terminates its final output line; retain the source's ending.
    if not source.endswith('\n') and rendered.endswith('\n'):
        rendered = rendered[:-1]
    lines = rendered.split('\n')
    stride = max(1, (len(lines) + 9999) // 10000)
    rows = []
    for index in range(0, len(lines), stride):
        content = '\n'.join(lines[index:index + stride])
        rows.append(f'<span class="source-line" data-source-line="{index}" data-source-end="{min(index + stride, len(lines))}" data-line-number="{index + 1}">{content}</span>')
    return f'<pre class="structured-source"><code class="language-{language}">' + '\n'.join(rows) + '</code></pre>', []


def render_source(source: str, document_format: str, base_directory: Path | None = None) -> dict:
    if document_format == 'PDF':
        from reader.pdf_documents import render_pdf
        return render_pdf(source)
    if len(source.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("The document is too large to preview (5 MB limit).")
    if document_format in {"HTML", "Word"}:
        html, headings = render_html(source, base_directory)
    elif document_format == "Markdown":
        html, headings = render_markdown(source, base_directory)
    else:
        html, headings = render_code_document(source, document_format)
    readable = BeautifulSoup(html, "html.parser").get_text(" ")
    from reader.openapi_documents import api_definition
    return {"html": html, "headings": headings, "words": len(re.findall(r"[\w\u200c]+", readable, re.UNICODE)),
            "api": api_definition(source, document_format)}


def load_document(path: Path, *, sample: bool = False) -> Document:
    path = path.expanduser().resolve()
    document_format = format_for_path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("This file exceeds 5 MB. Please open a smaller file.")
    if document_format in {'Word', 'PDF'}:
        if document_format == 'Word':
            from reader.word_documents import load_word
            source = load_word(raw, path.suffix)
        else:
            from reader.pdf_documents import load_pdf
            source = load_pdf(raw)
        return Document(id=str(path), name=path.name, path=str(path), **render_source(source, document_format, path.parent),
                        size=len(raw), encoding='Binary', sample=sample, format=document_format, source=source,
                        fingerprint=sha256(raw).hexdigest())
    codec, bom = "utf-8", b""
    for marker, candidate in [(b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"), (b"\xef\xbb\xbf", "utf-8")]:
        if raw.startswith(marker):
            codec, bom = candidate, marker
            break
    encoding = "UTF-16" if codec.startswith("utf-16") else "UTF-8"
    try:
        source = raw[len(bom):].decode(codec)
    except UnicodeError as error:
        raise ValueError("Unsupported text encoding. Please save the file as UTF-8 or UTF-16.") from error
    if "\x00" in source:
        raise ValueError("This file does not contain valid text.")
    newline = "\r\n" if "\r\n" in source else "\r" if "\r" in source else "\n"
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    rendered = render_source(source, document_format, path.parent)
    return Document(id=str(path), name=path.name, path=str(path), **rendered,
                    size=len(raw), encoding=encoding, sample=sample, format=document_format,
                    source=source, codec=codec, bom=bom.hex(), newline=newline, fingerprint=sha256(raw).hexdigest())
