# Changelog

## 0.1.0 - unreleased

Initial stack.

- OTel collector with one or two OTLP/HTTP receivers, environment tagging (resource and span), JSONL capture of all signals, traces to Phoenix.
- Phoenix (Postgres-backed); optional OpenObserve for metrics and log events (Compose profile `openobserve`).
- `init-env.sh` and preflight checks; per-launch content launchers (bash, PowerShell); example settings.
- Four test tiers: offline, settings hygiene, Docker smoke, Claude CLI.

Tested with Claude Code 2.1.283, `otel/opentelemetry-collector-contrib:0.140.0` (the binary reports 0.140.1), Phoenix 19.13.0.

### Known limitations (planned for 0.1.1)

- `.env.example` isn't pinned to LF line endings; a Windows checkout with CRLF can corrupt the generated `.env` (preflight's credential check catches the OpenObserve case).
- `make preflight` skips all port checks while any of this project's containers is running, so enabling the OpenObserve profile on a busy port gives a raw Docker bind error.
- Preflight reads only `.env`; shell variables that Compose also honours (such as an exported `COMPOSE_PROFILES`) bypass its checks.
- The JSONL capture files aren't rotated and grow without limit.
- The collector has no `memory_limiter`; a large burst under its 256 MB limit restarts it and drops in-flight data.
- `make up` doesn't wait for the collector to be healthy (its image has no shell for a Docker healthcheck), so a collector that keeps restarting isn't reported.
- `examples/project-settings.local.json` combines blocking claude.ai connectors with turning telemetry off; copy only the part you want.
- Findings 2, 5, 6 and 7 in `docs/findings.md` (and the interactive side of 3) are re-checked manually, not by a test.
- macOS and Linux desktops are expected to work but haven't been verified; WSL and native Windows have.
- The smoke test's log sender uses a deprecated OpenTelemetry SDK handler (a warning, no functional effect).
