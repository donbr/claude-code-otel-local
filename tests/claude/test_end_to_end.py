"""Real claude -p through the launcher -> an isolated stack -> Phoenix and OpenObserve (tier 4, needs Docker)."""

import json
import subprocess
import time
import uuid
from pathlib import Path

from tests.smoke.stack import Stack

REPO = Path(__file__).resolve().parents[2]


def wait_for(fn, timeout=90, interval=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result := fn():
            return result
        time.sleep(interval)
    return fn()


def test_launcher_prompt_reaches_phoenix_and_openobserve(tmp_path):
    marker = f"e2e-{uuid.uuid4().hex[:8]}"
    with Stack("openobserve", "none", tmp_path) as stack:
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        # --settings beats user settings, so this run exports to the isolated stack (findings §1).
        settings = cwd / "settings.json"
        settings.write_text(json.dumps({"env": {"OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{stack.ports['ENV_A_PORT']}"}}))
        subprocess.run(["bash", str(REPO / "launchers" / "claude-traced.sh"), "-p", f"Reply with the single word ok. {marker}",
                        "--tools", "", "--no-session-persistence", "--output-format", "json", "--settings", str(settings)],
                       cwd=cwd, check=True, capture_output=True, text=True, timeout=240)
        found = wait_for(lambda: stack.psql(
            "select count(*) from spans where name='claude_code.interaction' "
            f"and attributes->>'user_prompt' like '%{marker}%'") not in ("", "0"))
        assert found, "prompt text not found on a Phoenix interaction span"
        assert wait_for(lambda: stack.openobserve_search(marker, field="prompt")) > 0, \
            "user_prompt event with the prompt text not found in OpenObserve"
