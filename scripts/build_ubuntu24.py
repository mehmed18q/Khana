"""Build the Ubuntu 24.04+ installer in Docker without using host Python libraries."""

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-image-build", action="store_true")
    args = parser.parse_args()
    image = "khana-builder:ubuntu24"
    if not args.skip_image_build:
        subprocess.run(
            ["docker", "build", "-f", "packaging/ubuntu24.Dockerfile", "-t", image, "."],
            cwd=ROOT,
            check=True,
        )
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ubuntu24-", dir=build) as folder:
        stage = Path(folder)
        for name in ("reader", "scripts", "packaging", "tests", "examples"):
            shutil.copytree(
                ROOT / name, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        for name in (
            "main.py",
            "README.md",
            "CHANGELOG.md",
            "requirements.txt",
            "requirements-build.txt",
        ):
            shutil.copy2(ROOT / name, stage / name)
        command = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--shm-size=1g",
            "--mount",
            f"type=bind,source={stage},target=/work",
            "-e",
            "QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --no-sandbox",
            image,
        ]
        subprocess.run([*command, "python", "scripts/build_deb.py"], check=True)
        subprocess.run(
            [
                *command,
                "xvfb-run",
                "-a",
                "python",
                "tests/compatibility_smoke.py",
                "build/onedir/Khana/Khana",
            ],
            check=True,
        )
        destination = ROOT / "dist"
        destination.mkdir(exist_ok=True)
        for path in (stage / "dist").iterdir():
            shutil.copy2(path, destination / path.name)
            print(f"Ready: {destination / path.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
