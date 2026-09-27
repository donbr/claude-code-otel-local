import json
import os
from pathlib import Path

from tests.settings.keys import violations

FIXTURES = Path(__file__).parent / "fixtures"
ENDPOINT_A = os.environ.get("CLAUDE_ENDPOINT_A", "http://localhost:4318")
ENDPOINT_B = os.environ.get("CLAUDE_ENDPOINT_B", "http://localhost:4320")


def test_fixture_good_baseline_passes():
    assert violations(json.loads((FIXTURES / "good-baseline.json").read_text()), "http://localhost:4318") == []


def test_fixture_old_baseline_is_caught():
    found = violations(json.loads((FIXTURES / "old-baseline.json").read_text()), "http://localhost:4318")
    for expected in ("OTEL_EXPORTER_OTLP_HEADERS", "OTEL_LOG_USER_PROMPTS", "ARIZE_TRACE_ENABLED",
                     "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_LOGS_EXPORT_INTERVAL",
                     "extraKnownMarketplaces:langfuse-observability"):
        assert expected in found


def test_settings_a_matches_baseline(settings_a):
    found = violations(settings_a, ENDPOINT_A)
    assert not found, f"keys that break the baseline: {found}"


def test_settings_b_matches_baseline(settings_b):
    found = violations(settings_b, ENDPOINT_B)
    assert not found, f"keys that break the baseline: {found}"


def test_environments_agree_except_endpoint(settings_a, settings_b):
    a, b = settings_a.get("env", {}), settings_b.get("env", {})
    keys = {k for k in set(a) | set(b) if k.startswith(("OTEL_", "CLAUDE_CODE_ENABLE", "CLAUDE_CODE_ENHANCED"))}
    keys.discard("OTEL_EXPORTER_OTLP_ENDPOINT")
    assert sorted(k for k in keys if a.get(k) != b.get(k)) == []


def test_tool_details_counts_as_content_capture():
    settings = json.loads((FIXTURES / "good-baseline.json").read_text())
    settings["env"]["OTEL_LOG_TOOL_DETAILS"] = "1"
    assert "OTEL_LOG_TOOL_DETAILS" in violations(settings, "http://localhost:4318")


def test_non_numeric_metric_interval_is_reported_not_raised():
    settings = json.loads((FIXTURES / "good-baseline.json").read_text())
    settings["env"]["OTEL_METRIC_EXPORT_INTERVAL"] = "5s"
    assert "OTEL_METRIC_EXPORT_INTERVAL" in violations(settings, "http://localhost:4318")
