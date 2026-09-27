"""Settings vs process env: which telemetry keys a caller of `claude -p` can set per call.

Question: when a downstream Temporal worker project launches `claude -p` with extra environment variables, which
ones take effect, given that the user's ~/.claude/settings.json `env` block also sets telemetry keys?

Method: point a logs endpoint at a local OTLP/HTTP receiver and check whether it gets a request,
and whether the request body contains a marker from the prompt (proves OTEL_LOG_USER_PROMPTS).
The console exporter can't be used: it prints nothing in -p mode (checked 2026-09-27, CLI 2.1.283).

These tests run the real CLI under the subscription (one tiny prompt each, ~10-20 s). Opt in with
RUN_CLAUDE_CLI=1. Metered-billing variables are stripped, as the worker does.
"""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.claude.conftest import Receiver
from tests.redact import KeysOnly

METERED_CREDENTIAL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def run_claude(
    marker: str,
    extra_env: dict[str, str] | None = None,
    settings_env: dict | None = None,
    prompt: str | None = None,
):
    """Run one headless prompt from an empty directory, like the worker's neutral_cwd."""
    cwd = tempfile.mkdtemp(prefix="otel-precedence-")
    env = {k: v for k, v in os.environ.items() if k not in METERED_CREDENTIAL_ENV_VARS}
    env.update(extra_env or {})
    cmd = ["claude", "-p", prompt or f"Reply with the single word ok. {marker}", "--tools", ""]
    cmd += ["--no-session-persistence", "--output-format", "json"]
    if settings_env is not None:
        path = os.path.join(cwd, "settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"env": settings_env}, f)
        cmd += ["--settings", path]
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"claude -p failed: {result.stderr[-500:]}"


@pytest.fixture
def user_env() -> dict:
    path = Path(os.path.expanduser(os.environ.get("CLAUDE_SETTINGS_A", "~/.claude/settings.json")))
    return KeysOnly(json.loads(path.read_text()).get("env", {}))


def endpoint_override(user_env: dict, receiver: Receiver) -> tuple[str, str]:
    """The endpoint key user settings define, and the value that points it at the receiver.

    The per-signal logs key when present (the original OpenObserve baseline), otherwise the
    generic endpoint (the native-only baseline since 2026-09-27), whose base URL gets /v1/logs.
    """
    if "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" in user_env:
        return "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", receiver.url
    if "OTEL_EXPORTER_OTLP_ENDPOINT" in user_env:
        return "OTEL_EXPORTER_OTLP_ENDPOINT", receiver.base
    pytest.skip("user settings set no OTLP endpoint to override")


def test_settings_flag_overrides_user_settings(receiver, user_env):
    """Control: proves the receiver works and --settings beats ~/.claude/settings.json."""
    key, value = endpoint_override(user_env, receiver)
    marker = f"mk-{uuid.uuid4().hex[:8]}"
    run_claude(marker, settings_env={key: value, "OTEL_LOG_USER_PROMPTS": "1"})
    assert receiver.bodies, "no OTLP logs reached the receiver via --settings"
    assert receiver.saw("claude_code.user_prompt")
    assert receiver.saw(marker), "prompt text missing: OTEL_LOG_USER_PROMPTS not applied"


def test_process_env_cannot_override_a_key_user_settings_set(receiver, user_env):
    """Observed 2026-09-27: user settings win over the inherited process env for the same key."""
    key, value = endpoint_override(user_env, receiver)
    run_claude(f"mk-{uuid.uuid4().hex[:8]}", extra_env={key: value, "OTEL_LOG_USER_PROMPTS": "1"})
    assert not receiver.bodies, (
        "process env overrode user settings; the worker may now inject any key (update the plan)"
    )


def test_process_env_applies_a_key_user_settings_leave_unset(receiver, user_env):
    """The worker can add content flags per call, as long as user settings don't set them."""
    if "OTEL_LOG_USER_PROMPTS" in user_env:
        pytest.skip("user settings already set OTEL_LOG_USER_PROMPTS")
    marker = f"mk-{uuid.uuid4().hex[:8]}"
    run_claude(
        marker,
        extra_env={"OTEL_LOG_USER_PROMPTS": "1"},
        settings_env={"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": receiver.url},
    )
    assert receiver.bodies, "no OTLP logs reached the receiver"
    assert receiver.saw(marker), "process-env OTEL_LOG_USER_PROMPTS=1 was not applied"


def test_native_traces_and_content_on_subscription(receiver, user_env):
    """Max subscription, no plugins: native spans plus prompt and response text, all per call.

    Observed 2026-09-27: /v1/traces receives claude_code.interaction and claude_code.llm_request;
    /v1/logs receives user_prompt, api_request and assistant_response with the text.
    """
    per_call = {
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{receiver.base}/v1/traces",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_ASSISTANT_RESPONSES": "1",
    }
    # A key user settings already set to the same value is fine (the native-only baseline sets
    # the beta flag and traces exporter globally); a different value would silently win.
    conflicts = sorted(k for k, v in per_call.items() if k in user_env and user_env[k] != v)
    if conflicts:
        pytest.skip(f"user settings set {conflicts} to other values; process env would be ignored")
    head, tail = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    run_claude(
        head,
        prompt=f"Join these two tokens with no space and reply with only the result: {head} {tail}",
        extra_env=per_call,
        settings_env={"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": receiver.url},
    )
    assert "/v1/traces" in receiver.paths, "no spans exported"
    assert receiver.saw("claude_code.interaction")
    assert receiver.saw("claude_code.llm_request")
    assert receiver.saw("claude_code.assistant_response")
    assert receiver.saw(f"{head} {tail}"), "prompt text missing"
    assert receiver.saw(f"{head}{tail}"), "response text missing (joined tokens not in the prompt)"
