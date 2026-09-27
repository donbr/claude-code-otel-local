import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
}


def test_user_settings_example_is_the_baseline():
    env = json.loads((REPO / "examples" / "user-settings.json").read_text())["env"]
    assert env == BASELINE


def test_user_settings_example_has_no_content_or_headers():
    env = json.loads((REPO / "examples" / "user-settings.json").read_text())["env"]
    assert not [k for k in env if k.startswith("OTEL_LOG_") or "HEADERS" in k or k == "OTEL_RESOURCE_ATTRIBUTES"]


def test_project_example_uses_only_allowed_keys():
    data = json.loads((REPO / "examples" / "project-settings.local.json").read_text())
    assert {e["serverName"] for e in data["deniedMcpServers"]} >= {"claude.ai Gmail"}
    for key, value in data.get("env", {}).items():
        assert key.endswith("_EXPORTER") and value == "none", key
