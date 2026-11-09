"""Build Khana as a standalone Linux executable, including local web assets."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from hashlib import sha256, sha512
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def prepare_linux_libraries():
    # Include Qt's X11 support even on a Wayland host without XCB extras.
    # Ubuntu archive files and checksums are pinned to the build's OS version.
    cache = ROOT / "build/linux-libs"
    cache.mkdir(parents=True, exist_ok=True)
    for record in json.loads((ROOT / "packaging/linux-libs.json").read_text()):
        package = cache / record["file"]
        if not package.is_file() or sha512(package.read_bytes()).hexdigest() != record["sha512"]:
            subprocess.run(
                [
                    "curl",
                    "--connect-timeout",
                    "10",
                    "--max-time",
                    "60",
                    "--fail",
                    "--silent",
                    "--show-error",
                    record["url"],
                    "-o",
                    str(package),
                ],
                check=True,
            )
        if (
            package.stat().st_size != record["size"]
            or sha512(package.read_bytes()).hexdigest() != record["sha512"]
        ):
            raise RuntimeError(f"Downloaded library checksum mismatch: {package.name}")
        subprocess.run(["dpkg-deb", "--extract", str(package), str(cache / "root")], check=True)
    notices = cache / "root/usr/share/doc"
    if notices.is_dir():
        shutil.copytree(
            notices,
            ROOT / "build/licenses/linux-libs",
            dirs_exist_ok=True,
            ignore_dangling_symlinks=True,
        )


def collect_licenses():
    output = ROOT / "build" / "licenses"
    output.mkdir(parents=True, exist_ok=True)
    packages = [
        "PySide6",
        "PySide6_Addons",
        "PySide6_Essentials",
        "shiboken6",
        "markdown-it-py",
        "mdit-py-plugins",
        "mdurl",
        "Pygments",
        "nh3",
        "beautifulsoup4",
        "soupsieve",
        "typing_extensions",
        "PyInstaller",
        "PyMuPDF",
        "ruamel.yaml",
    ]
    notices = ["Khana bundles these third-party components:", ""]
    for name in packages:
        package = distribution(name)
        notices.append(f"{package.metadata['Name']} {package.version}")
        for file in package.files or []:
            if not any(part.lower().startswith(("license", "copying")) for part in file.parts):
                continue
            source = Path(package.locate_file(file))
            if source.is_file():
                target = output / name / str(file)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    notices += [
        "",
        "Mermaid 11.12.2: reader/web/vendor/MERMAID-LICENSE.txt",
        "Swagger UI 5.34.0: reader/web/vendor/SWAGGER-UI-LICENSE.txt; swagger-ui-bundle.js.LICENSE.txt",
        "Noto Sans Arabic: reader/web/fonts/LICENSE.txt",
    ]
    (output / "THIRD-PARTY.txt").write_text("\n".join(notices) + "\n", encoding="utf-8")


def desktop_quote(path):
    # Desktop Exec uses its own quoting rules, not shell quoting.
    value = str(path).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value.replace("\\", "\\\\") + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build an unpacked bundle for verification in build/onedir",
    )
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error(
            "This build script targets Linux x86_64. Build on the target operating system."
        )
    collect_licenses()
    prepare_linux_libraries()
    destination = ROOT / ("build/onedir" if args.onedir else "dist")
    env = {
        **os.environ,
        "KHANA_BUILD_MODE": "onedir" if args.onedir else "onefile",
        "PYINSTALLER_CONFIG_DIR": str(ROOT / "build" / "pyinstaller-cache"),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(destination),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            str(ROOT / "packaging" / "khana.spec"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    executable = destination / ("Khana/Khana" if args.onedir else "Khana")
    if not args.onedir:
        icon = destination / "khana.svg"
        shutil.copy2(ROOT / "reader" / "web" / "icon.svg", icon)
        launcher = destination / "io.khana.Khana.desktop"
        launcher.write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=Application",
                    "Version=1.0",
                    "Name=Khana",
                    "GenericName=Document and Text Editor",
                    "Comment=Read and write Persian and English documents",
                    f"Exec={desktop_quote(executable)} %F",
                    f"Icon={icon}",
                    "Terminal=false",
                    "Categories=Office;TextEditor;",
                    "MimeType=text/markdown;text/html;text/plain;application/json;application/yaml;text/yaml;application/xml;text/xml;application/pdf;application/msword;application/vnd.openxmlformats-officedocument.wordprocessingml.document;",
                    "StartupNotify=true",
                    "StartupWMClass=Khana",
                    "Keywords=Markdown;HTML;Editor;Persian;",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        digest = sha256()
        with executable.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        (destination / "SHA256SUMS").write_text(f"{digest.hexdigest()}  Khana\n", encoding="utf-8")
        (destination / "README.txt").write_text(
            "KHANA — LINUX x86_64\n\n"
            "Double-click Khana to open the app. Python and pip are not required.\n"
            "If your file manager asks, allow executing the file as a program.\n"
            "Khana is a single standalone executable; you can move it to another folder.\n"
            "The optional io.khana.Khana.desktop launcher uses this build folder's absolute path.\n"
            "Keep it here with khana.svg, or update Exec and Icon if you move the files.\n\n"
            "Built and tested for Ubuntu 26.04 x86_64. Not a Windows executable.\n"
            "The app starts fullscreen; press F11 to leave fullscreen.\n"
            "Startup can take a few seconds while the embedded runtime is unpacked.\n"
            "Settings: $XDG_CONFIG_HOME/Khana/Khana/settings.ini (normally ~/.config/Khana/Khana/settings.ini).\n"
            "Your documents stay where you save them.\n",
            encoding="utf-8",
        )
    print(f"Built: {executable}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
