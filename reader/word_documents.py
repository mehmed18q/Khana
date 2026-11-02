"""Word import/export through an isolated LibreOffice Writer process."""

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup


def convert(data: bytes, suffix: str, output: str) -> tuple[bytes, dict[str, bytes]]:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise ValueError(
            "Word support requires LibreOffice Writer. Install libreoffice-writer and reopen the document."
        )
    with tempfile.TemporaryDirectory(prefix="khana-word-") as folder:
        root = Path(folder)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (
            profile / "user/registrymodifications.xcu"
        ).write_text("""<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item></oor:items>""")
        source = root / ("document" + suffix)
        source.write_bytes(data)
        destination = root / "output"
        destination.mkdir()
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"}
        }
        env["SAL_USE_VCLPLUGIN"] = "svp"
        env["GSETTINGS_BACKEND"] = "memory"
        try:
            result = subprocess.run(
                [
                    executable,
                    "-env:UserInstallation=" + profile.as_uri(),
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--convert-to",
                    output,
                    "--outdir",
                    str(destination),
                    str(source),
                ],
                capture_output=True,
                timeout=60,
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(
                "Word conversion timed out. The original file was not changed."
            ) from error
        target = destination / ("document." + output.split(":")[0])
        if result.returncode or not target.is_file():
            raise ValueError(
                "LibreOffice could not convert this Word document. It may be encrypted or unsupported."
            )
        assets = {
            path.name: path.read_bytes()
            for path in destination.iterdir()
            if path != target and path.is_file()
        }
        return target.read_bytes(), assets


def load_word(data: bytes, suffix: str) -> str:
    converted, assets = convert(data, suffix, "html:HTML (StarWriter)")
    soup = BeautifulSoup(converted.decode("utf-8"), "html.parser")
    # Keep a portable editing source with embedded images; conversion files can go away.
    for image in soup.find_all("img"):
        name = Path(image.get("src", "")).name
        if name in assets:
            extension = Path(name).suffix.lower().lstrip(".")
            mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(extension, extension)
            image["src"] = f"data:image/{mime};base64," + base64.b64encode(assets[name]).decode(
                "ascii"
            )
    # Express common Writer character styles as semantic markup for the reader.
    for node in list(soup.find_all(["span", "font"])):
        style = node.get("style", "").lower()
        if "bold" in style or "font-weight: 700" in style:
            node.wrap(soup.new_tag("strong"))
        if "italic" in style:
            node.wrap(soup.new_tag("em"))
        if "underline" in style:
            node.wrap(soup.new_tag("u"))
    return str(soup)


def save_word(source: str, suffix: str) -> bytes:
    from reader.documents import render_html

    markup, _ = render_html(source)
    source = (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>' + markup + "</body></html>"
    )
    output = "doc:MS Word 97" if suffix.lower() == ".doc" else "docx:Office Open XML Text"
    data, _ = convert(source.encode("utf-8"), ".html", output)
    return data
