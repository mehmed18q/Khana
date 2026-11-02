"""Application resources, resolved from source or PyInstaller's extraction root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reader" / "web"
SAMPLE = ROOT / "examples" / "welcome.md"
