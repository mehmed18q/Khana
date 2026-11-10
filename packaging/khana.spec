# Build with scripts/build_linux.py. Both modes use identical analysis/data.
import os
from pathlib import Path

root = Path(SPECPATH).parent
onefile = os.environ.get("KHANA_BUILD_MODE", "onefile") == "onefile"
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[(str(path), ".") for path in (root / "build/linux-libs/root/usr/lib/x86_64-linux-gnu").glob("*.so.*")],
    datas=[
        (str(root / "reader" / "web"), "reader/web"),
        (str(root / "examples"), "examples"),
        (str(root / "build" / "licenses"), "licenses"),
        (str(root / "build" / "build-platform.json"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
options = dict(name="Khana", debug=False, bootloader_ignore_signals=False,
               strip=False, upx=False, console=False)
if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, name="Khana", strip=False, upx=False)
