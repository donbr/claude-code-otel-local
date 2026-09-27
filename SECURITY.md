# Security

## What this stack exposes

- **Localhost only.** Every published port (the OTLP receivers, Phoenix, OpenObserve) binds to `127.0.0.1`. Postgres is reachable only on the internal Compose network.
- **No authentication in front of the data.** The OTLP receivers and Phoenix accept anyone who can reach them, and OpenObserve has only its root login from `.env`, over plain HTTP. That is safe only because the ports bind to `127.0.0.1`: don't change the bindings to `0.0.0.0`, publish these ports through a tunnel or reverse proxy, or run the stack on a shared host whose other users you don't trust.
- **Secrets stay in `.env`.** `scripts/init-env.sh` generates the Phoenix database password and the OpenObserve root password, writes `.env` with mode `600`, and refuses to overwrite an existing one. `.env` is gitignored. Claude Code settings hold no credentials: OpenObserve's auth token lives only in the collector's environment.
- **Images are pinned** in `compose.yaml`: by digest, except the collector, which uses an exact version tag (`0.140.0`).

## What content capture stores

By default Claude Code redacts prompts, replies and tool content. When you launch through `launchers/claude-traced.*`, it doesn't: whatever the session reads or writes (file contents, command output, prompts, replies, possibly secrets) is copied, in plain text, to:

- `data/out/traces.jsonl`, `logs.jsonl`, `metrics.jsonl` (gitignored, on your disk);
- Phoenix's Postgres volume (retention `PHOENIX_RETENTION_DAYS`, default 14);
- OpenObserve's volume, if enabled (retention `OPENOBSERVE_RETENTION_DAYS`, default 30).

Identifiers such as `user.email`, account ids and `organization.id` are exported even with content capture off. Delete `data/out/` and run `docker compose down -v` to remove everything.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** on this repository (Security → Report a vulnerability). Don't open a public issue for security problems.
