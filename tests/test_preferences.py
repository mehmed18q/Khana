"""Invalid persisted values must not prevent the rest of the preferences loading."""

import json
import unittest

from reader.preferences import DEFAULTS, normalize_preferences


class PreferencesTests(unittest.TestCase):
    def test_invalid_root_uses_independent_defaults(self):
        for value in (None, [], "invalid", 17):
            with self.subTest(value=value):
                preferences = normalize_preferences(value)
                self.assertEqual({key: preferences[key] for key in DEFAULTS}, DEFAULTS)
        first = normalize_preferences({})
        first["sidebar"]["files"]["open"] = False
        self.assertTrue(normalize_preferences({})["sidebar"]["files"]["open"])

    def test_one_bad_value_does_not_discard_other_preferences(self):
        preferences = normalize_preferences({"theme": "dark", "fontSize": "invalid", "wide": True})
        self.assertEqual(preferences["theme"], "dark")
        self.assertEqual(preferences["fontSize"], DEFAULTS["fontSize"])
        self.assertTrue(preferences["wide"])

    def test_numeric_values_are_finite_and_bounded(self):
        for value in (float("nan"), float("inf"), -float("inf"), None, True, {}, []):
            with self.subTest(value=value):
                preferences = normalize_preferences(
                    {
                        key: value
                        for key in ("fontSize", "lineHeight", "previewZoom", "sidebarWidth")
                    }
                )
                for key in ("fontSize", "lineHeight", "previewZoom", "sidebarWidth"):
                    self.assertEqual(preferences[key], DEFAULTS[key])
                json.dumps(preferences, allow_nan=False)
        preferences = normalize_preferences(
            {"fontSize": "100", "lineHeight": -5, "previewZoom": 301, "sidebarWidth": 999}
        )
        self.assertEqual(
            (preferences["fontSize"], preferences["lineHeight"], preferences["previewZoom"]),
            (24, 1.6, 300),
        )
        self.assertEqual(preferences["sidebarWidth"], 560)
        self.assertEqual(normalize_preferences({"sidebarWidth": 0})["sidebarWidth"], 220)

    def test_unknown_fields_and_malformed_sidebar_are_repaired(self):
        preferences = normalize_preferences(
            {
                "theme": [],
                "wide": "false",
                "unused": 1,
                "sidebar": {"files": {"open": False, "weight": float("nan")}, "outline": []},
            }
        )
        self.assertNotIn("unused", preferences)
        self.assertFalse(preferences["wide"])
        self.assertEqual(preferences["sidebar"]["files"], {"open": False, "weight": 1})
        self.assertEqual(preferences["sidebar"]["outline"], {"open": True, "weight": 1})
