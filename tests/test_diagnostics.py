"""Verify local logging in an isolated process so global hooks do not leak."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DiagnosticsTests(unittest.TestCase):
    def test_logs_rotate_and_capture_python_worker_and_fatal_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            script = """
import faulthandler, logging, os, resource, sys
from reader.diagnostics import configure, log_directory
from reader.ui.workers import LoadTask
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
directory = configure(sys.argv[1])
assert directory == log_directory()
assert configure('/unused/settings.ini') == directory
logger = logging.getLogger('reader')
handler = logger.handlers[0]
handler.maxBytes = 2000
for i in range(50):
    logger.warning('rotation check %s %s', i, 'x' * 120)
LoadTask(directory / 'missing.md').run()
try:
    raise ValueError('unhandled-smoke')
except ValueError:
    sys.excepthook(*sys.exc_info())
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.abort()
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(folder / "settings.ini")],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertLess(result.returncode, 0, result.stderr)
            logs = folder / "logs"
            self.assertTrue((logs / "khana.log.1").exists())
            self.assertLessEqual(len(list(logs.glob("khana.log*"))), 4)
            content = "\n".join(path.read_text() for path in logs.glob("khana.log*"))
            self.assertIn("Could not load", content)
            self.assertIn("unhandled-smoke", content)
            self.assertIn("Worker load", content)
            self.assertIn("Fatal Python error: Aborted", (logs / "crash.log").read_text())


if __name__ == "__main__":
    unittest.main()
