"""Failing tier-2/tier-4 tests must print key names only, never setting values or raw telemetry."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRET = "SECRETVALUE" + "123"


def run_pytest(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
                          cwd=REPO, capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_failing_settings_test_does_not_print_values(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Basic {SECRET}"}}))
    out = run_pytest("tests/settings/test_hygiene.py::test_settings_a_matches_baseline",
                     env={"CLAUDE_SETTINGS_A": str(settings)})
    assert out.returncode == 1, "the settings test should fail on this file"
    assert "OTEL_EXPORTER_OTLP_HEADERS" in out.stdout
    assert SECRET not in out.stdout + out.stderr


def test_failing_receiver_assert_does_not_print_bodies(tmp_path):
    test = tmp_path / "test_leak.py"
    test.write_text(
        "from tests.claude.conftest import Receiver\n"
        "def test_leak():\n"
        # Assembled at runtime so the failing line's source text doesn't contain the secret.
        f"    r = Receiver(base='x', bodies=[b'user.email ' + b'{SECRET[:6]}' + b'{SECRET[6:]}'], paths=['/v1/logs'])\n"
        "    assert not r.bodies\n"
    )
    out = run_pytest(str(test), "--rootdir", str(REPO), env={"PYTHONPATH": str(REPO)})
    assert out.returncode == 1
    assert SECRET not in out.stdout + out.stderr
