"""Static guard against silent ``NameError`` regressions.

Background
----------
A previous bug (uploads.py: ``normalized_client_name`` instead of
``resolved_client_name``; missing ``http_404`` import) caused every upload
in the authenticated app to crash with a 500 *after* commit but *before*
the anonymisation background task could be scheduled. The unit tests
present at the time only exercised the validation/auth paths so the
regression slipped through.

This test runs ruff's ``F821`` rule (undefined name) against the whole
``app/`` package and fails the build if a name is referenced without
being defined or imported. It runs in milliseconds, requires no DB and
no fixtures, and would have caught the original bug instantly.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"


def test_no_undefined_names_in_app_package():
    """``ruff --select F821`` must report zero issues for ``app/``.

    F821 catches things like the historical ``normalized_client_name`` and
    missing ``http_404`` import that broke the upload → anonymise pipeline.
    """
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(APP_DIR), "--select", "F821"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        "ruff F821 found undefined names in app/.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
