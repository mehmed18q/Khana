"""Require the oldest supported Ubuntu ABI for distributable Linux builds."""

import json
import platform
import re
import subprocess
from pathlib import Path

DEBIAN_REVISION = "1"
BUILD_TARGET = {"distribution": "ubuntu", "release": "24.04", "architecture": "amd64"}
MAX_GLIBC = (2, 39)


def require_build_host():
    info = platform.freedesktop_os_release()
    if (
        info.get("ID") != BUILD_TARGET["distribution"]
        or info.get("VERSION_ID") != BUILD_TARGET["release"]
        or platform.machine() != "x86_64"
    ):
        raise RuntimeError(
            "Release builds require Ubuntu 24.04 amd64. Use: python scripts/build_ubuntu24.py"
        )


def audit_glibc(bundle):
    """Check real ELF requirements, including Python and bundled native modules."""
    maximum = (0, 0)
    for path in Path(bundle).rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        symbols = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        versions = [
            tuple(map(int, item.split("."))) for item in re.findall(r"GLIBC_(\d+\.\d+)", symbols)
        ]
        required = max(versions, default=(0, 0))
        if required > MAX_GLIBC:
            raise RuntimeError(
                f"{path} needs GLIBC_{'.'.join(map(str, required))}; rebuild on Ubuntu 24.04"
            )
        maximum = max(maximum, required)
    return ".".join(map(str, maximum))


def validate_bundle(bundle):
    record = Path(bundle) / "_internal/build-platform.json"
    if not record.is_file() or json.loads(record.read_text()) != BUILD_TARGET:
        raise RuntimeError(
            "Missing Ubuntu 24.04 build record; rebuild with scripts/build_ubuntu24.py"
        )
    return audit_glibc(bundle)
