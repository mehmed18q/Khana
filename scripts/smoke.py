"""Run desktop smoke checks sequentially and retain per-check logs and results."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_CHECKS = (
    "desktop",
    "workspace",
    "tab_drag",
    "sidebar",
    "api_requests",
    "api_transport",
    "openapi",
    "editor",
    "builders",
    "library",
    "formats",
    "zoom",
    "beautify",
)
PACKAGE_CHECKS = ("bundle", "deb")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGKILL)
    else:
        process.kill()
    process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checks", nargs="*", help="Check names; omit to run the source desktop suite"
    )
    parser.add_argument("--timeout", type=int, default=240, help="Maximum seconds per check")
    parser.add_argument(
        "--output", type=Path, help="Log directory (defaults to artifacts/checks/<UTC timestamp>)"
    )
    args = parser.parse_args()
    checks = args.checks or DESKTOP_CHECKS
    unknown = set(checks) - set(DESKTOP_CHECKS + PACKAGE_CHECKS)
    if unknown:
        parser.error("Unknown checks: " + ", ".join(sorted(unknown)))
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = (args.output or ROOT / "artifacts" / "checks" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"Logs: {output}", flush=True)
    for name in checks:
        started = time.monotonic()
        log = output / f"{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "tests" / f"{name}_smoke.py")],
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            try:
                status = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                stop_process(process)
                status = 124
            except KeyboardInterrupt:
                stop_process(process)
                raise
        result = {
            "test": name,
            "status": status,
            "seconds": round(time.monotonic() - started, 1),
            "log": str(log),
        }
        results.append(result)
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"{'PASS' if status == 0 else 'FAIL'} {name} ({result['seconds']}s)", flush=True)
        if status:
            print(log.read_text(encoding="utf-8", errors="replace")[-6000:], flush=True)
    return int(any(result["status"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
