# CLAUDE.md

Local, native-only OpenTelemetry stack for Claude Code: collector → JSONL + Phoenix (+ optional OpenObserve). Design: `docs/design/2026-09-27-claude-code-otel-local-design.md`; plan and its "As built" deviations: `docs/design/2026-09-27-claude-code-otel-local-v1.md`.

## This repo is public

- No personal data in any tracked file: emails (except `@example.com`), `/home/<name>`, `C:\Users\<name>`, macOS user paths, session UUIDs, tokens, or names of private projects. `tests/offline/test_public_readiness.py` enforces it; stage new files before running it.
- Never commit `.env` or `data/`. Only `.env.example`, with empty secrets.
- Personal setup (your paths, second-environment settings file) goes in `CLAUDE.local.md`, which is gitignored.

## Collector config

- Compose passes `base.yaml` plus two overlay slots as repeated `--config` files. The merge combines maps but **replaces lists**.
- So environment pipelines (`traces/a`, `traces/b`, …) end in `forward/*` connectors, and overlays may only add new keys or replace the fan-out exporter lists (`metrics/out`, `logs/out`). Never make an overlay edit an environment pipeline.
- The environment tag goes on the resource **and** every span: Phoenix drops resource attributes.
- After any change under `collector/`: `uv run pytest tests/offline/test_collector_graph.py tests/smoke/test_validate.py`.

## Security invariants

- Every published port binds `127.0.0.1`. Nothing in front of the receivers, Phoenix or OpenObserve adds auth (see `SECURITY.md`).
- Images pinned by digest (collector by exact tag). CI actions pinned to full commit SHAs with a `# vX.Y.Z` comment; runners pinned (no `*-latest`). `tests/offline/test_env_and_compose.py` and `test_ci.py` check this.
- Content capture is per launch only, via `launchers/claude-traced.{sh,ps1}`. User settings must not set the `OTEL_LOG_*` content flags (`tests/settings/keys.py`).
- Secrets live only in `.env` (mode 600) and the collector's environment, never in Claude Code settings.

## Tests

| Command | Tier | Needs |
|---|---|---|
| `make verify` | 1 offline + 3 Docker smoke | Docker |
| `make verify-settings` | 2 settings hygiene | `CLAUDE_SETTINGS_A` (default `~/.claude/settings.json`), optional `CLAUDE_SETTINGS_B` |
| `make verify-claude` | 4 Claude CLI | Claude Code + subscription |

- Tests print key names only, never setting values or receiver bodies.
- PowerShell tests skip unless `pwsh` is on PATH or `PWSH` points at one (from WSL, the Windows `pwsh.exe` works).
- Smoke stacks use their own project name, random ports and a temp data dir; they never touch a running stack.

## Conventions

- Never pass `--bare` to `claude`.
- When the build deliberately differs from the plan, add a line to the plan's "As built" section; user-visible changes and known limitations go in `CHANGELOG.md`.
- `docs/findings.md` is pinned to Claude Code 2.1.283. Re-check with tier 4 before changing a finding.
- `.ps1` files are CRLF; everything else LF (`.gitattributes`).
- Scripts are stdlib-only Python or bash; dev dependencies live in `pyproject.toml` (`uv`).
