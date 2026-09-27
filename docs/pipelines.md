# Pipelines: `claude -p` workers

Guidance for programs that run Claude Code headless (`claude -p`) as a subprocess, such as workflow workers, while the user settings carry the baseline from [`examples/user-settings.json`](../examples/user-settings.json).

## Set only per-call keys

User settings win over the process env for any key they set ([findings §1](findings.md#1-precedence)). A worker can therefore add only keys the baseline leaves unset:

| Key | Purpose |
|---|---|
| `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT` | Content capture for this call |
| `ENABLE_BETA_TRACING_DETAILED=1`, `BETA_TRACING_ENDPOINT` | Reply on the `llm_request` span (headless needs no allowlisting). Point the endpoint at the same collector |
| `OTEL_RESOURCE_ATTRIBUTES` | Per-call attributes such as workflow and run ids, or `openinference.project.name` to choose the Phoenix project |
| `TRACEPARENT` (and `TRACESTATE`) | Parent the CLI's spans under the caller's span. `-p` and the Agent SDK read it; interactive sessions ignore it |

Don't put `OTEL_RESOURCE_ATTRIBUTES` in user settings: it would silently override every worker's per-call value. The collector adds the environment tag instead.

## Keep the context small

```bash
claude -p "…" --strict-mcp-config --disable-slash-commands
```

- On one `Read` task these flags cut cache-creation tokens from **547,782 to 4,247**. Almost all of the difference was MCP tool definitions ([findings §7](findings.md#7-context-noise)).
- They matter more with detailed tracing, which emits one `tool` log event per available tool definition.
- Plugins and hooks still load with these flags.
- claude.ai connectors can also be blocked per project with `deniedMcpServers` ([`examples/project-settings.local.json`](../examples/project-settings.local.json)).

## Never `--bare`

Don't use `--bare`. It breaks subscription authentication for headless runs.

## Other notes

- Run each call from a neutral working directory if the worker shouldn't pick up a repo's project settings.
- Settings are read at process start, so each new `claude -p` call picks up changes to user settings; a long-running interactive session doesn't.
- Detailed tracing adds a lot of log volume; filter the `tool` definition events in the collector if you keep logs long-term.
