"""Prevent publishing newer-host native code under the Ubuntu 24.04 label."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.linux_build_support import (
    BUILD_TARGET,
    audit_glibc,
    require_build_host,
    validate_bundle,
)


class LinuxPackagingTests(unittest.TestCase):
    def test_build_requires_supported_base_and_architecture(self):
        for release, machine in (("26.04", "x86_64"), ("24.04", "aarch64")):
            with (
                patch(
                    "scripts.linux_build_support.platform.freedesktop_os_release",
                    return_value={"ID": "ubuntu", "VERSION_ID": release},
                ),
                patch("scripts.linux_build_support.platform.machine", return_value=machine),
                self.assertRaises(RuntimeError),
            ):
                require_build_host()
        with (
            patch(
                "scripts.linux_build_support.platform.freedesktop_os_release",
                return_value={"ID": "ubuntu", "VERSION_ID": "24.04"},
            ),
            patch("scripts.linux_build_support.platform.machine", return_value="x86_64"),
        ):
            require_build_host()

    def test_audit_rejects_one_newer_native_library(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "python.so"
            path.write_bytes(b"\x7fELFfixture")
            with (
                patch(
                    "scripts.linux_build_support.subprocess.check_output",
                    return_value="Name: GLIBC_2.43\nName: GLIBC_2.39",
                ),
                self.assertRaisesRegex(RuntimeError, "GLIBC_2.43"),
            ):
                audit_glibc(folder)
            with patch(
                "scripts.linux_build_support.subprocess.check_output",
                return_value="Name: GLIBC_2.2.5\nName: GLIBC_2.39",
            ):
                self.assertEqual(audit_glibc(folder), "2.39")

    def test_missing_or_wrong_build_record_is_not_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(RuntimeError):
                validate_bundle(root)
            (root / "_internal").mkdir()
            record = root / "_internal/build-platform.json"
            record.write_text(json.dumps({**BUILD_TARGET, "release": "26.04"}))
            with self.assertRaises(RuntimeError):
                validate_bundle(root)
            record.write_text(json.dumps(BUILD_TARGET))
            with patch("scripts.linux_build_support.audit_glibc", return_value="2.39"):
                self.assertEqual(validate_bundle(root), "2.39")


if __name__ == "__main__":
    unittest.main()
