"""Native configuration location; reading preferences are normalized separately."""

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from reader.resources import ROOT


def default_settings_path() -> Path:
    # A one-file executable extracts resources to a temporary, read-only-in-
    # practice location. Preferences must survive removal of that directory.
    if getattr(sys, "frozen", False):
        return (
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
            / "settings.ini"
        )
    return ROOT / ".local" / "settings.ini"


def library_path(settings_path: Path | None = None) -> Path:
    """The SQLite reading library lives beside the settings file."""
    return Path(settings_path or default_settings_path()).with_name("library.sqlite3")
