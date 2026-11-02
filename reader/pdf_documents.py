"""PDF pages and conservative text replacement; no OCR or layout reconstruction."""

import json
import tempfile
from functools import lru_cache
from hashlib import sha256
from html import escape
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pymupdf

_temporary = tempfile.TemporaryDirectory(prefix="khana-pdf-")
CACHE = Path(_temporary.name)
_lock = RLock()  # MuPDF calls must not run concurrently in worker threads.
_records = {}


def load_pdf(data: bytes) -> str:
    with _lock, pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("This PDF is password-protected. Open an unlocked copy.")
        identifier = uuid4().hex
        path = CACHE / (identifier + ".pdf")
        path.write_bytes(data)
        pages = []
        editable = bool(document.permissions & pymupdf.PDF_PERM_MODIFY)
        for page in document:
            blocks = []
            for block in page.get_text(
                "dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
            )["blocks"]:
                if block["type"] != 0:
                    continue
                spans = [span for line in block["lines"] for span in line["spans"]]
                text = "\n".join(
                    "".join(span["text"] for span in line["spans"]) for line in block["lines"]
                )
                if not text.strip():
                    continue
                box = pymupdf.Rect(block["bbox"])
                simple = (
                    editable
                    and not page.rotation
                    and box.width > 8
                    and box.height > 6
                    and all(tuple(line["dir"]) == (1, 0) for line in block["lines"])
                )
                blocks.append(
                    {
                        "id": f"{page.number}:{len(blocks)}",
                        "text": text,
                        "bbox": list(box),
                        "size": spans[0]["size"],
                        "color": spans[0]["color"],
                        "editable": simple,
                    }
                )
            # Overlapping text regions are kept read-only to avoid replacing neighboring text.
            for i, block in enumerate(blocks):
                rect = pymupdf.Rect(block["bbox"])
                if any(
                    i != j and (rect & pymupdf.Rect(other["bbox"])).get_area() > 1
                    for j, other in enumerate(blocks)
                ):
                    block["editable"] = False
            pages.append({"width": page.rect.width, "height": page.rect.height, "blocks": blocks})
        _records[identifier] = {"path": path, "pages": pages}
        return json.dumps({"pdfId": identifier, "edits": {}}, ensure_ascii=False)


def _state(source):
    state = json.loads(source)
    record = _records.get(state.get("pdfId"))
    if not record or not isinstance(state.get("edits"), dict):
        raise ValueError("The PDF session is unavailable. Reopen the document.")
    known = {block["id"]: block for page in record["pages"] for block in page["blocks"]}
    for identifier, text in state["edits"].items():
        if (
            identifier not in known
            or not known[identifier]["editable"]
            or not isinstance(text, str)
            or len(text) > 20000
            or "\x00" in text
        ):
            raise ValueError("This PDF text region cannot be edited.")
    return state, record


@lru_cache(maxsize=6)
def _edited_path(source):
    state, record = _state(source)
    if not state["edits"]:
        return record["path"]
    target = CACHE / (sha256(source.encode()).hexdigest() + ".pdf")
    with pymupdf.open(record["path"]) as document:
        for number, meta in enumerate(record["pages"]):
            changes = [
                block
                for block in meta["blocks"]
                if block["id"] in state["edits"] and state["edits"][block["id"]] != block["text"]
            ]
            if not changes:
                continue
            page = document[number]
            # Do not apply a document author's unrelated redaction annotations.
            for annotation in list(page.annots() or []):
                if annotation.type[0] == pymupdf.PDF_ANNOT_REDACT:
                    raise ValueError("This page has pending redactions and is read-only in Khana.")
            for block in changes:
                page.add_redact_annot(block["bbox"], fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0)
            for block in changes:
                text = state["edits"][block["id"]]
                if not text:
                    continue
                rtl = any("\u0600" <= char <= "\u06ff" for char in text)
                css = f"body {{ margin:0; font-family:sans-serif; font-size:{block['size']}pt; color:#{block['color']:06x}; }}"
                markup = (
                    '<div dir="'
                    + ("rtl" if rtl else "ltr")
                    + '">'
                    + escape(text).replace("\n", "<br>")
                    + "</div>"
                )
                spare, _ = page.insert_htmlbox(block["bbox"], markup, css=css, scale_low=0.65)
                if spare < 0:
                    raise ValueError(
                        "The replacement text does not fit this PDF region. Use shorter text."
                    )
        document.save(target, garbage=4, deflate=True)
    return target


def save_pdf(source: str) -> bytes:
    with _lock:
        return _edited_path(source).read_bytes()


def render_pdf(source: str) -> dict:
    with _lock:
        state, record = _state(source)
        _edited_path(source)  # Validate all changes before presenting a successful preview.
        output, headings, words = [], [], 0
        for number, page in enumerate(record["pages"]):
            title = f"Page {number + 1}"
            headings.append({"id": f"pdf-page-{number}", "title": title, "level": 1})
            output.append(
                f'<figure class="pdf-page" id="pdf-page-{number}" data-pdf-page="{number}" style="aspect-ratio:{page["width"]}/{page["height"]}"><img class="pdf-image" alt="{title}"><span class="pdf-loading">Loading {title.lower()}…</span>'
            )
            for block in page["blocks"]:
                text = state["edits"].get(block["id"], block["text"])
                words += len(text.split())
                x0, y0, x1, y1 = block["bbox"]
                style = f"left:{x0 / page['width'] * 100}%;top:{y0 / page['height'] * 100}%;width:{(x1 - x0) / page['width'] * 100}%;height:{(y1 - y0) / page['height'] * 100}%;"
                editable = "true" if block["editable"] else "false"
                output.append(
                    f'<div class="pdf-block" data-pdf-block="{block["id"]}" data-editable="{editable}" style="{style}" title="'
                    + ("Edit text" if block["editable"] else "Read-only text")
                    + '"><span class="pdf-text">'
                    + escape(text)
                    + "</span></div>"
                )
            output.append("</figure>")
        return {"html": "".join(output), "headings": headings, "words": words}


def page_image(source: str, number: int) -> str:
    with _lock:
        path = _edited_path(source)
        target = CACHE / f"{path.stem}-{number}.png"
        if not target.exists():
            with pymupdf.open(path) as document:
                page = document[number]
                scale = min(2, 1400 / max(page.rect.width, page.rect.height))
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(target)
        return target.as_uri()
