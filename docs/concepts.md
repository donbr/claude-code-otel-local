# Concepts

How Claude Code's telemetry settings interact, where each signal goes, and what the content flags change. Observed on Claude Code 2.1.283; see [findings.md](findings.md) for the evidence.

## Settings scopes

| Scope | File | Can turn telemetry **on**, choose endpoints, capture content? | Can turn it **off**? |
|---|---|---|---|
| User | `~/.claude/settings.json` (Windows: `C:\Users\<user>\.claude\settings.json`) | **Yes** | Yes |
| Project (shared) | `<repo>/.claude/settings.json` | **No**: ignored, with a startup warning | Yes (`OTEL_*_EXPORTER=none`) |
| Project (local) | `<repo>/.claude/settings.local.json` | **No**: ignored, with a startup warning | Yes |
| Shell / process env | `export …` before `claude`, or a launcher | **Only for keys user settings leave unset.** User settings win on conflicts | Only for unset keys |
| `--settings <file>` | any JSON file | Yes; overrides user settings | Yes |
| Managed settings | organization-managed | Yes; the docs say they remove conflicting developer OTLP variables | Yes |

### Rules of thumb

- **Global plumbing goes in user settings:** the on/off switch, exporters, endpoint and protocol. That's the baseline in [`examples/user-settings.json`](../examples/user-settings.json). It sets one generic `OTEL_EXPORTER_OTLP_ENDPOINT` and no headers.
- **Project files are for turning things off.** [`examples/project-settings.local.json`](../examples/project-settings.local.json) shows the telemetry-off form, and `deniedMcpServers` entries that keep claude.ai connectors out of one project.
- **Per-launch extras go in the process env.** Content capture and detailed tracing work that way because the baseline leaves those keys unset. The launchers rely on this.
- **Settings are read once, when a process starts.** A running session and its subagents keep the config they started with. New sessions and new `claude -p` calls pick up changes.
- **Tag environments in the collector, not in settings.** A global `OTEL_RESOURCE_ATTRIBUTES` in user settings would override any per-call attributes a pipeline sets, because user settings win over the process env.

## Signal routing

| Signal | JSONL (`data/out/`) | Phoenix | OpenObserve (profile) |
|---|---|---|---|
| Traces | `traces.jsonl` | yes | no |
| Metrics | `metrics.jsonl` | no (Phoenix returns 405) | yes |
| Log events | `logs.jsonl` | no (Phoenix returns 405) | yes |

- Claude Code talks only to the collector. The collector's receivers listen on `ENV_A_PORT` (and `ENV_B_PORT` in dual-env mode).
- Every record gets `deployment.environment.name` as a resource attribute. Spans also get it as a span attribute, because Phoenix discards resource attributes.
- The JSONL capture is always on. It's the audit copy, and without OpenObserve it's the only home of the `assistant_response` event, which carries the reply in interactive sessions.

## Content flags

| Flag | Adds |
|---|---|
| `OTEL_LOG_USER_PROMPTS=1` | Prompt text on the `interaction` span and the `user_prompt` event |
| `OTEL_LOG_ASSISTANT_RESPONSES=1` | Reply text in the `assistant_response` log event |
| `OTEL_LOG_TOOL_DETAILS=1` | Tool parameters (paths, commands), MCP tool names, `skill_name` on the tool span |
| `OTEL_LOG_TOOL_CONTENT=1` | Tool output as a `tool.output` span event |

The launchers set all four for one launch. `DETAILED=1` / `-Detailed` also sets `ENABLE_BETA_TRACING_DETAILED=1` and `BETA_TRACING_ENDPOINT` (the value of `OTEL_EXPORTER_OTLP_ENDPOINT`, else `http://localhost:4318`). The docs describe that pair as one that also changes where logs and traces go; pointing it at the same collector keeps everything in place.

Identifiers such as `user.email`, account ids and `organization.id` ship whatever the flags say.

## Interactive vs headless detailed tracing

| Feature | Headless `-p` | Interactive |
|---|---|---|
| Prompt text on the `interaction` span | yes | yes |
| Tool span + `tool.output` event | yes | yes |
| Reply in the `assistant_response` log event | yes | yes |
| `response.model_output` on the `llm_request` span | yes | **no** |
| `tool_input` on the tool span, `claude_code.hook` spans, system-prompt preview | yes | **no** |

The Claude Code monitoring docs say detailed beta tracing in interactive sessions also requires the organization to be allowlisted, while `-p` and Agent SDK sessions don't. How to get allowlisted isn't documented. In interactive sessions, read the reply from the `assistant_response` event (JSONL or OpenObserve).
