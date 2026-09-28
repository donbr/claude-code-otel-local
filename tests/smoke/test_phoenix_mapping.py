"""Tier 3: Phoenix shows Claude Code's prompt and reply in its Input/Output fields (collector mapping).

Checks what Phoenix's REST API returns, which is what its UI and MCP server read, not raw storage.
"""

import json
import time
import urllib.request

import pytest

from tests.smoke.otlp_send import send_claude_like
from tests.smoke.stack import Stack
from tests.smoke.test_smoke import jsonl_records, wait_for

pytestmark = pytest.mark.docker


def phoenix_spans(stack: Stack, marker: str) -> dict[str, dict]:
    """Span name -> Phoenix's view of it (span_kind + flattened attributes) for spans tagged with marker."""
    url = f"http://127.0.0.1:{stack.ports['PHOENIX_PORT']}/v1/projects/default/spans?limit=100&attribute=smoke.id:{marker}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp).get("data", [])
    except OSError:
        return {}
    return {s["name"]: s for s in data}


def test_prompt_reply_kind_and_tokens_reach_phoenix(tmp_path):
    with Stack("none", "none", tmp_path) as stack:
        marker = f"oi-{int(time.time())}"
        send_claude_like(stack.ports["ENV_A_PORT"], marker, prompt=f"prompt {marker}", reply=f"reply {marker}")
        spans = wait_for(lambda: (s := phoenix_spans(stack, marker)) and len(s) == 3 and s)
        assert spans, "spans never reached Phoenix"

        interaction = spans["claude_code.interaction"]
        assert interaction["span_kind"] == "AGENT"
        assert interaction["attributes"]["input.value"] == f"prompt {marker}"

        llm = spans["claude_code.llm_request"]
        assert llm["span_kind"] == "LLM"
        assert llm["attributes"]["output.value"] == f"reply {marker}"
        assert llm["attributes"]["llm.token_count.prompt"] == 112  # input + cache read + cache write
        assert llm["attributes"]["llm.token_count.total"] == 117

        tool = spans["claude_code.tool"]
        assert tool["span_kind"] == "TOOL"
        assert tool["attributes"]["tool.name"] == "Bash"
        assert "input.value" not in tool["attributes"]  # no tool flags, nothing to show

        # The audit copy stays exactly as Claude Code sent it.
        for rattrs, attrs in jsonl_records(stack.data_dir / "out" / "traces.jsonl", marker):
            assert not {"input.value", "output.value", "openinference.span.kind"} & attrs.keys()


def test_redacted_content_leaves_input_and_output_empty(tmp_path):
    with Stack("none", "none", tmp_path) as stack:
        marker = f"oi-red-{int(time.time())}"
        send_claude_like(stack.ports["ENV_A_PORT"], marker, prompt="<REDACTED>", reply="<REDACTED>")
        spans = wait_for(lambda: (s := phoenix_spans(stack, marker)) and len(s) == 3 and s)
        assert spans, "spans never reached Phoenix"
        assert "input.value" not in spans["claude_code.interaction"]["attributes"]
        assert spans["claude_code.interaction"]["span_kind"] == "AGENT"
        # Phoenix may synthesise its own output.value on LLM spans; it must not be the redaction marker.
        assert spans["claude_code.llm_request"]["attributes"].get("output.value") != "<REDACTED>"


@pytest.mark.parametrize("mode,expected_in,expected_out,mime", [
    ("detailed", '{{"command":"echo {m}"}}', '{{"stdout":"{m}","stderr":""}}', "application/json"),
    ("flags", "echo {m}", "{m}\n", None),
], ids=["detailed-tracing", "tool-flags"])
def test_tool_input_and_output_reach_phoenix(tmp_path, mode, expected_in, expected_out, mime):
    with Stack("none", "none", tmp_path) as stack:
        marker = f"oi-tool-{mode}-{int(time.time())}"
        send_claude_like(stack.ports["ENV_A_PORT"], marker, prompt="p", reply="r", tool_mode=mode)
        spans = wait_for(lambda: (s := phoenix_spans(stack, marker)) and len(s) == 3 and s)
        assert spans, "spans never reached Phoenix"
        attrs = spans["claude_code.tool"]["attributes"]
        assert attrs["input.value"] == expected_in.format(m=marker)  # "[TOOL INPUT: …]" line stripped
        assert attrs["output.value"] == expected_out.format(m=marker)
        assert attrs.get("input.mime_type") == mime


def test_values_already_set_upstream_are_never_overwritten(tmp_path):
    preset = {"input.value": "upstream-in", "output.value": "upstream-out",
              "llm.token_count.prompt_details.cache_read": 7, "llm.token_count.prompt_details.cache_write": 8}
    with Stack("none", "none", tmp_path) as stack:
        marker = f"oi-preset-{int(time.time())}"
        send_claude_like(stack.ports["ENV_A_PORT"], marker, prompt="p", reply="r", tool_mode="detailed", preset=preset)
        spans = wait_for(lambda: (s := phoenix_spans(stack, marker)) and len(s) == 3 and s)
        assert spans, "spans never reached Phoenix"
        tool = spans["claude_code.tool"]["attributes"]
        assert (tool["input.value"], tool["output.value"]) == ("upstream-in", "upstream-out")
        assert "input.mime_type" not in tool and "output.mime_type" not in tool
        llm = spans["claude_code.llm_request"]["attributes"]
        assert llm["output.value"] == "upstream-out"
        assert (llm["llm.token_count.prompt_details.cache_read"], llm["llm.token_count.prompt_details.cache_write"]) == (7, 8)
