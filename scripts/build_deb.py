"""Build the installable Ubuntu package, including desktop and icon registration."""

from __future__ import annotations

import argparse
import math
import platform
import shutil
import subprocess
import sys
from hashlib import md5, sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reader import APP_ID, APP_NAME, VERSION


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def write_icons(destination):
    # Export the existing vector logo at native dock/menu/HiDPI sizes. SVG and
    # PNG variants share the same themed name as the desktop application ID.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    source = ROOT / "reader/web/icon.svg"
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError("The application logo is not valid SVG.")
    theme = destination / "usr/share/icons/hicolor"
    copy(source, theme / f"scalable/apps/{APP_ID}.svg")
    for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        target = theme / f"{size}x{size}/apps/{APP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target)):
            raise RuntimeError(f"Could not write {target}")
    copy(source, destination / f"usr/share/pixmaps/{APP_ID}.svg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse the current unpacked build (must match the source)",
    )
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("Build this package on Ubuntu 26.04 x86_64.")
    if not args.skip_build:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_linux.py"), "--onedir"], check=True
        )
    bundle = ROOT / "build/onedir/Khana"
    if not (bundle / "Khana").is_file():
        parser.error("Missing unpacked build; run without --skip-build.")
    bundle_version = subprocess.check_output(
        [str(bundle / "Khana"), "--version"], text=True
    ).strip()
    if bundle_version != f"{APP_NAME} {VERSION}":
        parser.error(
            f"Unpacked build reports {bundle_version!r}; expected {APP_NAME} {VERSION}. "
            "Rebuild without --skip-build."
        )
    version = VERSION + "-1"
    staging = ROOT / "build/deb" / f"khana_{version}_amd64"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copytree(bundle, staging / "opt/khana", symlinks=True)
    command = staging / "usr/bin/khana"
    command.parent.mkdir(parents=True)
    command.symlink_to("/opt/khana/Khana")
    desktop = staging / f"usr/share/applications/{APP_ID}.desktop"
    copy(ROOT / f"packaging/{APP_ID}.desktop", desktop)
    subprocess.run(["desktop-file-validate", str(desktop)], check=True)
    write_icons(staging)
    copy(ROOT / "README.md", staging / "usr/share/doc/khana/README.md")
    (staging / "usr/share/doc/khana/THIRD-PARTY.txt").write_text(
        "Runtime component licenses are installed in /opt/khana/_internal/licenses.\n"
        "Mermaid: /opt/khana/_internal/reader/web/vendor/MERMAID-LICENSE.txt\n"
        "Swagger UI: /opt/khana/_internal/reader/web/vendor/SWAGGER-UI-LICENSE.txt; swagger-ui-bundle.js.LICENSE.txt\n"
        "Noto Sans Arabic: /opt/khana/_internal/reader/web/fonts/LICENSE.txt\n"
        "Spelling dictionaries: /opt/khana/_internal/reader/web/dictionaries/README.md and LICENSE-*.txt\n",
        encoding="utf-8",
    )
    # Bytecode/runtime .so files are intentionally kept as emitted by the
    # verified PyInstaller build. No install hooks run user code or change
    # preferred applications. System dpkg triggers refresh desktop/icon caches.
    files = sorted(path for path in staging.rglob("*") if path.is_file() and not path.is_symlink())
    installed_size = math.ceil(sum(path.stat().st_size for path in files) / 1024)
    control = staging / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: khana\nVersion: {version}\nArchitecture: amd64\n"
        "Section: editors\nPriority: optional\n"
        "Maintainer: Khana local build <noreply@localhost>\n"
        f"Installed-Size: {installed_size}\n"
        "Depends: libc6 (>= 2.43), libgl1, libegl1, desktop-file-utils, hicolor-icon-theme, libreoffice-writer\n"
        "Description: Khana - document and text editor for Persian and English\n"
        " A local desktop reader and editor with smart bidirectional text,\n"
        " synchronized preview, Word, PDF, structured text, tables and flowcharts.\n"
        " Includes its own Python and Qt runtime. Built for Ubuntu 26.04 amd64.\n",
        encoding="utf-8",
    )
    hashes = []
    for path in files:
        digest = md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes.append(f"{digest.hexdigest()}  {path.relative_to(staging)}")
    (control / "md5sums").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    package = destination / f"khana_{version}_amd64.deb"
    subprocess.run(
        [
            "dpkg-deb",
            "--root-owner-group",
            "-Zxz",
            "-z6",
            "--threads-max=2",
            "--build",
            str(staging),
            str(package),
        ],
        check=True,
    )
    digest = sha256()
    with package.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    (destination / (package.name + ".sha256")).write_text(
        f"{digest.hexdigest()}  {package.name}\n", encoding="utf-8"
    )
    (destination / "INSTALL.txt").write_text(
        f"KHANA {VERSION} — UBUNTU 26.04 (64-BIT)\n\n"
        "Install this package with the system package installer, or run:\n"
        f"  sudo apt install ./" + package.name + "\n\n"
        "Installation needs your Ubuntu administrator password.\n"
        "Then search for Khana in Show Applications and launch it.\n"
        "Right-click its icon and choose Pin to Dash / Add to Favorites.\n"
        "Close any old portable Khana window before launching the installed version.\n"
        "No Git repository or Python installation is required.\n\n"
        "Remove the installed app: sudo apt remove khana\n"
        "Preferences and documents are kept when the package is removed.\n"
        "Preferences: ~/.config/Khana/Khana/settings.ini\n"
        "Library, stars, marks and notes: ~/.config/Khana/Khana/library.sqlite3\n",
        encoding="utf-8",
    )
    print(f"Installer: {package}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
