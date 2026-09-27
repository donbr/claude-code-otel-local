"""Re-check findings that need a real headless claude -p (docs/findings.md)."""

import uuid

import pytest

from tests.claude.test_precedence import run_claude, user_env  # noqa: F401  (fixture re-export)


def test_detailed_headless_puts_response_on_llm_request(receiver, user_env):  # noqa: F811
    """findings §3: in -p, detailed beta tracing puts the reply on llm_request as response.model_output."""
    per_call = {
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{receiver.base}/v1/traces",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        "ENABLE_BETA_TRACING_DETAILED": "1",
        "BETA_TRACING_ENDPOINT": receiver.base,
        # As DETAILED=1 on the launcher: detailed tracing together with the content flags.
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_ASSISTANT_RESPONSES": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
    }
    conflicts = sorted(k for k, v in per_call.items() if k in user_env and user_env[k] != v)
    if conflicts:
        pytest.skip(f"user settings set {conflicts} to other values; process env would be ignored")
    head, tail = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    run_claude(head, prompt=f"Join these two tokens with no space and reply with only the result: {head} {tail}",
               extra_env=per_call)
    assert "/v1/traces" in receiver.paths, "no spans exported"
    assert receiver.saw("response.model_output"), "no response.model_output attribute on any span"
    assert receiver.saw(f"{head}{tail}"), "reply text missing from the exported spans"
