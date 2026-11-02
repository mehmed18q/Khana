"""Probe real GNOME/GIO registration in an isolated XDG data directory."""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import Gdk, GioUnix, Gtk

application_id = "io.khana.Khana"
entry = GioUnix.DesktopAppInfo.new(application_id + ".desktop")
assert entry, "Installed desktop entry is not discoverable"
assert entry.get_name() == "Khana"
assert entry.should_show(), "Application is hidden from the menu"
assert entry.get_icon().to_string() == application_id
assert entry.get_startup_wm_class() == "Khana"
assert any(application_id + ".desktop" in group for group in GioUnix.DesktopAppInfo.search("Khana"))
assert "text/markdown" in entry.get_supported_types()
assert "text/html" in entry.get_supported_types()
assert "application/pdf" in entry.get_supported_types()
assert "application/json" in entry.get_supported_types()
assert "application/msword" in entry.get_supported_types()
Gtk.init()
theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
assert theme.has_icon(application_id), "The themed logo is not discoverable"
icon = theme.lookup_icon(
    application_id, None, 64, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_REGULAR
)
assert icon.get_file().get_path().startswith(sys.argv[1]), icon.get_file().get_path()
print(
    json.dumps(
        {
            "name": entry.get_name(),
            "search": GioUnix.DesktopAppInfo.search("Khana"),
            "icon": icon.get_file().get_path(),
            "wm_class": entry.get_startup_wm_class(),
        }
    )
)
