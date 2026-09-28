# Phoenix: what you see, and how agents query it

Phoenix gets every trace from the collector. This page covers what each Claude Code span carries, what Phoenix shows for it, and how a person or an agent finds it. Versions: Claude Code 2.1.283, Phoenix 19.13.0.

## No text by default

Claude Code redacts prompts and replies unless the session sets the content flags ([concepts](concepts.md#content-flags)). A normal session therefore shows structure, timing and tokens only. Text appears only for a session started through a launcher, or a worker call that sets the per-call keys ([pipelines](pipelines.md)).

| Where | Prompt | Reply |
|---|---|---|
| Phoenix **Input** (interaction span) | with `OTEL_LOG_USER_PROMPTS=1` | — |
| Phoenix **Output** (`llm_request` span) | — | headless `-p` with `ENABLE_BETA_TRACING_DETAILED=1` and `BETA_TRACING_ENDPOINT` ([findings §3](findings.md)) |
| Phoenix **Input/Output** (tool spans) | full JSON with detailed tracing; otherwise the command or file path with `OTEL_LOG_TOOL_DETAILS=1` | full JSON with detailed tracing; otherwise the output with `OTEL_LOG_TOOL_CONTENT=1` |
| OpenObserve / `data/out/logs.jsonl` (`user_prompt`, `assistant_response` events) | with `OTEL_LOG_USER_PROMPTS=1` | with `OTEL_LOG_ASSISTANT_RESPONSES=1`, interactive or headless |

Interactive replies never reach a span, so in Phoenix they stay empty; read them from the `assistant_response` log event.

## The mapping

Phoenix fills its Input and Output panes only from the OpenInference attributes `input.value` and `output.value`, and takes the span kind from `openinference.span.kind`. It converts some OpenTelemetry `gen_ai.*` keys itself (model name, and LLM/TOOL kind from `gen_ai.request.model` and `gen_ai.tool.call.id`), but none of those carry text. Claude Code uses its own attribute names, so the collector's `transform/openinference` processor (`collector/base.yaml`) copies them:

| Span | Claude Code attribute | Set for Phoenix |
|---|---|---|
| `claude_code.interaction` | — | `openinference.span.kind=AGENT` |
| | `user_prompt` (skipped if `<REDACTED>`) | `input.value`, `input.mime_type=text/plain` |
| `claude_code.llm_request` | — | `openinference.span.kind=LLM` |
| | `response.model_output` (skipped if `<REDACTED>`) | `output.value`, `output.mime_type=text/plain` |
| | `input_tokens + cache_read_tokens + cache_creation_tokens` | `llm.token_count.prompt` (OpenInference counts cache tokens as prompt tokens) |
| | `cache_read_tokens`, `cache_creation_tokens` | `llm.token_count.prompt_details.cache_read`, `.cache_write` |
| | `output_tokens` | `llm.token_count.completion`; `llm.token_count.total` = prompt + completion |
| `claude_code.tool` | `tool_name` | `openinference.span.kind=TOOL`, `tool.name` |
| | `tool_input` (detailed tracing; JSON after a `[TOOL INPUT: X]` line, which is stripped) | `input.value`, `input.mime_type=application/json` |
| | otherwise `full_command` or `file_path` (`OTEL_LOG_TOOL_DETAILS`) | `input.value` |
| | `new_context` (detailed tracing; JSON after a `[TOOL RESULT: X]` line, which is stripped) | `output.value`, `output.mime_type=application/json` |
| | otherwise the `tool.output` span event's `output` or `content` (`OTEL_LOG_TOOL_CONTENT`) | `output.value` |

Rules:

- The mapping runs only on the `traces/phoenix` branch. `data/out/traces.jsonl` keeps exactly what Claude Code sent.
- It never overwrites a value that is already set, so a caller that sends OpenInference attributes itself wins.
- The original attributes stay on the span; the mapped ones are copies.
- `tests/smoke/test_phoenix_mapping.py` checks all of this against Phoenix's API.

Not mapped: the `llm_request` span has no request text (Claude Code doesn't emit the messages it sends), and `claude_code.tool.execution` / `claude_code.tool.blocked_on_user` stay `UNKNOWN`.

## Span tree and attribute keys

One trace per interaction:

```
claude_code.interaction            (one per user turn; a subagent's turn nests under its Agent tool span)
├── claude_code.llm_request        (one per model call)
├── claude_code.tool               (one per tool call)
│   ├── claude_code.tool.blocked_on_user
│   └── claude_code.tool.execution
└── claude_code.hook               (user-level hooks, including in -p calls)
```

Every span carries `deployment.environment.name` (added by the collector), `session.id`, `user.id`, `user.email`, `user.account_uuid`, `organization.id`, `terminal.type`, `span.type`.

| Span | Other keys |
|---|---|
| `claude_code.interaction` | `user_prompt`, `user_prompt_length`, `interaction.sequence`, `interaction.duration_ms` |
| `claude_code.llm_request` | `model`, `gen_ai.request.model`, `gen_ai.system`, `gen_ai.response.id`, `gen_ai.response.finish_reasons`, `request_id`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `ttft_ms`, `duration_ms`, `stop_reason`, `success`, `query_source_safe`, `agent_id`; `response.model_output` with detailed tracing |
| `claude_code.tool` | `tool_name`, `tool_use_id`, `gen_ai.tool.call.id`, `duration_ms`, `agent_id`; with `OTEL_LOG_TOOL_DETAILS` also `full_command`, `bash_argv0`, `bash_command_class` or `file_path`; with detailed tracing also `tool_input`, `new_context`; event `tool.output` (`output` or `content`) with `OTEL_LOG_TOOL_CONTENT` |
| `claude_code.tool.execution` | `success`, `error`, `error_class`, `tool_use_id`, `duration_ms` |
| `claude_code.tool.blocked_on_user` | `decision`, `source`, `duration_ms` |
| `claude_code.hook` | `hook_event`, `hook_name`, `num_hooks`, `num_success`, `duration_ms` |

## Joining spans to log events

The reply of an interactive session, cost, and per-request API details live in log events (OpenObserve, `logs.jsonl`), not on spans. Join them by:

- `session.id`: on every span and every log event.
- `request_id`: on the `llm_request` span and on the `api_request` and `assistant_response` events for the same model call.
- `prompt.id`: on the `user_prompt` event and the events of that turn.

## Projects

Spans go to Phoenix's `default` project unless the resource carries `openinference.project.name` (set it per call with `OTEL_RESOURCE_ATTRIBUTES`; see [pipelines](pipelines.md)).

Phoenix assigns a project when a trace first arrives and ignores the name on later spans of that trace. A `claude -p` started from inside another Claude Code session inherits that session's `TRACEPARENT`, joins its trace, and lands in *its* project. Workers should drop an inherited `TRACEPARENT`/`TRACESTATE` unless they mean to nest.

## Querying (people and agents)

Phoenix is on `http://localhost:${PHOENIX_PORT}` (default 6006), with no authentication; it is reachable only from this machine.

**REST.** Filter spans by name, kind, trace, time and attribute (`attribute=key:value`, repeatable, dotted keys):

```bash
# LLM spans from the Windows environment in the default project
curl "http://localhost:6006/v1/projects/default/spans?span_kind=LLM&attribute=deployment.environment.name:windows&limit=50"
# Everything from one Claude Code session
curl "http://localhost:6006/v1/projects/default/spans?attribute=session.id:<session-id>"
```

Each span in the response has `name`, `span_kind`, `context.trace_id`, `parent_id`, `start_time`, `end_time`, `status_code` and `attributes` (flattened dotted keys, including `input.value` and `output.value`).

**GraphQL** (`/graphql`). `Project.spans(filterCondition: …)` accepts Python-like conditions such as `span_kind == 'LLM'` or `'refund' in input.value`. Attributes are stored nested, so filter with `attributes['deployment']['environment']['name'] == 'wsl'`; the flat dotted form matches nothing and reports no error.

**MCP.** Phoenix has a built-in MCP server at `http://localhost:6006/mcp` (generated from the REST API; on by default since Phoenix 19.0). For Claude Code:

```bash
claude mcp add --transport http phoenix http://localhost:6006/mcp
```

The npm package `@arizeai/phoenix-mcp` (tools such as `list-projects`, `get-spans`, `get-trace`) works too.
