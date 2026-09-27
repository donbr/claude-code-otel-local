# Dual environment: WSL and native Windows on one Docker engine

Docker Desktop runs one engine that both WSL and Windows reach on `localhost`. One stack with two receivers serves both environments. Each receiver tags what it gets, so traces from both land in one Phoenix, and you can tell them apart.

| Environment | Claude Code sends to | Tag (`deployment.environment.name`) |
|---|---|---|
| WSL | `http://localhost:4318` (`ENV_A_PORT`) | `ENV_A_NAME`, e.g. `wsl` |
| Windows | `http://localhost:4320` (`ENV_B_PORT`) | `ENV_B_NAME`, e.g. `windows` |

## `.env`

```ini
ENV_A_NAME=wsl
ENV_B_NAME=windows
COLLECTOR_OVERLAY_1=dual-env
# optional
COLLECTOR_OVERLAY_2=openobserve
COMPOSE_PROFILES=openobserve
```

Then `make up` from the WSL checkout. The `ENV_B_PORT` mapping is always published, but nothing listens on it without the `dual-env` overlay.

## Settings on each side

WSL and Windows have separate user settings files. `claude.exe` on Windows reads `C:\Users\<user>\.claude\settings.json`. Use the same baseline ([`examples/user-settings.json`](../examples/user-settings.json)) in both, with one difference on Windows:

```json
"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4320"
```

`make verify-settings` checks both files when you point it at them:

```bash
CLAUDE_SETTINGS_B=/mnt/c/Users/<user>/.claude/settings.json make verify-settings
```

It checks that both match the baseline, that each has its own endpoint (`CLAUDE_ENDPOINT_A` / `CLAUDE_ENDPOINT_B`, default `:4318` / `:4320`), and that they agree on every other telemetry key.

## Windows launcher

```powershell
pwsh -File .\launchers\claude-traced.ps1                 # interactive, content on
pwsh -File .\launchers\claude-traced.ps1 -Detailed -p "…"  # headless, response on spans
```

- It sets the content flags for this launch and restores the previous values on exit.
- Arguments pass straight through via `$args`. A `param()` block would make PowerShell treat claude's `-p` as ambiguous with its common parameters.
- With `-Detailed`, `BETA_TRACING_ENDPOINT` comes from `OTEL_EXPORTER_OTLP_ENDPOINT` **in the shell**, else `http://localhost:4318`. Claude Code applies the settings `env` block inside its own process, so the shell usually doesn't have that value. On Windows in dual-env mode, set it in your PowerShell profile, or the detailed traces go to the WSL receiver:
  ```powershell
  $env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://localhost:4320'
  ```
- You can copy the launcher to a fixed place such as `C:\Users\<user>\.claude\scripts\`. Refresh the copy when this repo changes it.

## Messaging between WSL and Windows sessions

Claude Code sessions in the two environments can't see each other locally. To message a Windows session from WSL (or the reverse), enable **Remote Control** on it. It then registers under a generated name, not its `/rename` name; list sessions to find it.

## Checking the tag

```bash
docker compose exec -T phoenix-db psql -U phoenix -d phoenix -Atc \
  "select attributes->'deployment'->'environment'->>'name', count(*) from spans group by 1"
```
