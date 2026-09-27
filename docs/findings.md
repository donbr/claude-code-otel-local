# Findings

Observed behaviour of Claude Code's native telemetry. These are observations, not documented guarantees: each is pinned to the version it was seen on, and re-checked by the named test where one exists.

- **Observed on:** Claude Code **2.1.283**, 2026-09-27, Max subscription, WSL (Ubuntu) and native Windows.
- **Stack:** `otel/opentelemetry-collector-contrib:0.140.0`, Phoenix 19.13.0.
- **Re-run:** `make verify-claude` (tier 4) and `make verify` (tier 3). "Manual" means no automated test re-checks it yet.

| # | Finding | Evidence | Re-checked by |
|---|---|---|---|
| 1 | Precedence | local `claude -p` runs against a test receiver | `tests/claude/test_precedence.py` (3 tests) |
| 2 | Project scope can only turn telemetry off | startup warning in a project that set `OTEL_*` keys | manual |
| 3 | Response on spans, headless only | configuration matrix runs; an interactive Windows session | `test_detailed_headless_puts_response_on_llm_request` (headless side); interactive side manual |
| 4 | Where content lands | configuration matrix runs | `test_native_traces_and_content_on_subscription`, `test_launcher_prompt_reaches_phoenix_and_openobserve` |
| 5 | Skills | skill probe runs | manual |
| 6 | Subagents | configuration matrix, subagent run | manual |
| 7 | Context noise | configuration matrix, token counts | manual |
| 8 | Phoenix accepts traces only | direct POSTs to Phoenix 19.13.0 and 20.16.0 | `tests/smoke/test_smoke.py::test_phoenix_rejects_logs_and_metrics` (19.13.0) |

## 1. Precedence

- User `settings.json` `env` beats the inherited process env for the same key.
- The process env applies only to keys user settings leave unset. That's why the launchers work: the baseline doesn't set the content flags.
- `--settings <file>` overrides both.
- The Claude Code docs don't state the user-settings-vs-shell order. Secondary sources that say "the shell wins" are contradicted by this measurement.

## 2. Project scope

Project `.claude/settings.json` and `.claude/settings.local.json` cannot enable telemetry or set endpoints; Claude Code ignores those keys and warns at startup. They can turn telemetry off (`OTEL_*_EXPORTER=none`), with no warning.

## 3. Response on spans

- In headless `-p`, detailed beta tracing (`ENABLE_BETA_TRACING_DETAILED=1` + `BETA_TRACING_ENDPOINT`) together with the content flags (as `DETAILED=1` on the launchers sets them) puts the reply on `claude_code.llm_request` as `response.model_output`, with no allowlisting.
- With `BETA_TRACING_ENDPOINT` set, logs and traces are sent there as OTLP/JSON with chunked transfer encoding. The collector accepts that; a hand-rolled receiver must read chunked bodies.
- Interactive sessions with the same variables got prompt and tool content but no `response.model_output`, `tool_input` or hook spans. The docs say interactive detailed tracing needs organization allowlisting; how to get it isn't documented.

## 4. Where content lands

With the content flags on:
- the prompt is on the `interaction` span (and the `user_prompt` event);
- tool output is a `tool.output` span event;
- the reply is in the `assistant_response` **log event**, not on a span (except with headless detailed tracing, item 3).

## 5. Skills

- Loading a skill emits a `skill_activated` log event with `skill.name`, `skill.source`, `plugin.name`, `marketplace.name` and `invocation_trigger`.
- Cost and token metrics after activation carry a `skill.name` label, so per-skill cost is available by default.
- The tool span shows only `tool_name=Skill` by default. `OTEL_LOG_TOOL_DETAILS=1` adds `skill_name` to it, which is the only way the skill name reaches Phoenix (traces only).

## 6. Subagents

- A subagent's model calls and tools nest under the parent's `Agent` tool span, all in one trace.
- The `query_source` attribute separates parent calls (`sdk`, or the main loop) from subagent calls (for example `agent:builtin:general-purpose`).
- Subagents run in the parent's process and use its telemetry config.

## 7. Context noise

- Per-call context is dominated by MCP tool definitions, not the system prompt (about 6.7 K characters either way).
- `--strict-mcp-config --disable-slash-commands` cut cache-creation tokens from **547,782 to 4,247** on one `Read` task (689 tool-definition events to 3).
- Plugins and hooks still load with those flags.
- Much of the remaining weight came from claude.ai connectors. `deniedMcpServers` in project settings blocks them per project; see [`examples/project-settings.local.json`](../examples/project-settings.local.json).
- Single-run token counts vary between identical runs; treat them as indicative.

## 8. Phoenix accepts traces only

Phoenix's OTLP endpoint returns **405** for `/v1/logs` and `/v1/metrics` on 19.13.0 and 20.16.0. Metrics and log events therefore go to the JSONL files and, optionally, OpenObserve.
