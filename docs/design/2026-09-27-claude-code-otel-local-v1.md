# claude-code-otel-local v1 Implementation Plan

> **Status:** Tasks 1–8 implemented; Task 9 = review and public release; Task 10 = generic migration guidance. Where the build differs from the steps below, see [As built (v0.1.0)](#as-built-v010).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, native-only Claude Code telemetry stack with an OTel collector (one or two receivers, environment tagging), JSONL capture, Postgres-backed Phoenix, optional OpenObserve, per-launch content launchers, four test tiers and docs. Release it public (MIT) after an owner `/code-review ultra` pass.

**Architecture:**
- **Compose project.** One Docker Compose project; OpenObserve is behind the `openobserve` profile.
- **Collector config.** A base config plus up to two overlays, passed as repeated `--config` files. Environment pipelines end in `forward` connectors, so overlays only add keys, or replace the fan-out exporter lists.
- **Tooling.** A stdlib-only preflight script and bash/PowerShell launchers. Pytest covers four tiers: offline, settings, Docker smoke, Claude CLI.

**Tech Stack:**
- `otel/opentelemetry-collector-contrib:0.140.0`
- Phoenix 19.13.0 (digest-pinned), `postgres:16.15-alpine` (digest-pinned), OpenObserve (digest-pinned)
- Python 3.11+ via `uv`, with `pytest`, `pyyaml`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`
- bash, PowerShell 7, GNU make

**Spec:** [`2026-09-27-claude-code-otel-local-design.md`](2026-09-27-claude-code-otel-local-design.md)

## Global Constraints

- **Repo:** `~/claude-code-otel-local` (WSL). GitHub `claude-code-otel-local`, **public from the first push**, license **MIT**.
- **Pinned images:**
  - Collector: `otel/opentelemetry-collector-contrib:0.140.0`
  - Phoenix: `arizephoenix/phoenix@sha256:e61b2ec06fa1f2f96fb9ffbdf55a7484290931188f82b05393def69b85eeaba2`
  - Postgres: `postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`
  - OpenObserve: `public.ecr.aws/zinclabs/openobserve@sha256:e1ff0445fab3e748ac4cf630308cc8493579e50d19ad255bb3a3b8c1b710aaf7`
- **Host ports:** every published port binds `127.0.0.1`. Defaults: `ENV_A_PORT=4318`, `ENV_B_PORT=4320`, `PHOENIX_PORT=6006`, `OPENOBSERVE_PORT=5080`.
- **Environment tag:** `deployment.environment.name` goes on the **resource and every span**, because Phoenix drops resource attributes.
- **No credentials in Claude Code settings.** OpenObserve auth lives only in the collector's environment (`OPENOBSERVE_BASIC_AUTH`).
- **Baseline user-settings `env`:**
  - `CLAUDE_CODE_ENABLE_TELEMETRY=1`
  - `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`
  - `OTEL_TRACES_EXPORTER=otlp`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`
  - `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`
- **Personal data:** no emails (except `@example.com`), `/home/<name>`, `C:\Users\<name>`, UUIDs or tokens in any tracked file.
- **Test output:** tests print key names only, never setting values.
- **Never** `--bare` in any `claude` invocation.
- **Findings** are pinned to Claude Code **2.1.283**.
- **Commits:** end every commit message with the session attribution lines.
- **Line endings:** `.gitattributes` enforces LF for `*.sh`, `*.yaml`, `*.yml`, `*.py`, `*.md`, `Makefile`; CRLF for `*.ps1`.

## Review Focus

1. **Host port already in use** (another local observability stack on 6006, or an older collector on 4318). Expect `make up` to stop with a message naming the port and variable, not a Docker bind error. Test: `test_check_ports_reports_busy_port` in Task 3.
2. **Missing or partial `.env`.** Expect `make up`/preflight to refuse and point at `scripts/init-env.sh`; Compose must not start Postgres with an empty password. Tests: `test_check_env_requires_secrets` and `test_compose_requires_db_password` in Task 3.
3. **Bind-mounted `data/out` created by Docker as root, or a host UID other than 1000.** The file exporter can't write and capture silently stops. Expect preflight to create `data/out` owned by the user, and Compose to run the collector as `HOST_UID:HOST_GID` from `.env`. Tests: `test_init_env_writes_uid_gid_and_data_dir` (Task 3); the smoke assertion that JSONL files are non-empty (Task 4).
4. **`openobserve` overlay set without the `openobserve` Compose profile, or the reverse.** The collector would retry against a missing host forever, or OpenObserve would run unused. Expect preflight to reject the mismatch. Test: `test_check_env_openobserve_overlay_requires_profile` in Task 3.
5. **Launchers edited or checked out on Windows with CRLF**, which breaks `bash`. Expect `.gitattributes` to keep `*.sh` LF. Test: `test_gitattributes_line_endings` in Task 1.


## As built (v0.1.0)

The steps below are the plan as written. The build differs in these deliberate ways, each found while running the steps:

- **OpenObserve limits.** It refuses a retention below 3 days, and it panics at startup unless the root password has lower, upper, digit and special characters. The smoke stack uses 3 days; `init-env.sh` and the smoke harness append `-Aa1` to the generated password; preflight rejects a retention below 3, a weak password, and an `OPENOBSERVE_BASIC_AUTH` that doesn't match `email:password`.
- **More preflight checks.** `ENV_B_PORT` is checked in every mode (Compose always publishes it), and `data/out` must be writable and owned by `HOST_UID`.
- **Smoke ports.** The harness picks ports from 20000–32000 and retries with new ports on "ports are not available": Docker Desktop can't forward ports that Windows/Hyper-V reserves in the dynamic range. A failed `compose up` tears down and reports Compose's error.
- **Finding 8 re-check.** `test_phoenix_rejects_logs_and_metrics` (tier 3) checks Phoenix returns 405 for logs and metrics.
- **End-to-end test.** `test_launcher_prompt_reaches_phoenix_and_openobserve` brings up its own isolated stack (with the OpenObserve profile) and points the launcher at it with `--settings`, instead of using the user's running stack. It checks the prompt in Phoenix and the `user_prompt` event in OpenObserve.
- **Tier-4 receiver.** It reads chunked uploads: with `BETA_TRACING_ENDPOINT` set, Claude Code sends OTLP/JSON with chunked transfer encoding. Receiver bodies and settings fixtures are wrapped so failing tests print key names only.
- **Reply on the span needs detailed tracing plus the content flags.** `test_detailed_headless_puts_response_on_llm_request` (tier 4) checks it; `docs/findings.md` §3 says so.
- **Pinning.** `postgres` is pinned by digest (`postgres:16.15-alpine@sha256:…`); CI uses a read-only token, actions pinned to commit SHAs (`actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.2.0, both Node 24), and a pinned `ubuntu-24.04` runner instead of `ubuntu-latest`.
- **Launchers.** The PowerShell launcher exits 127 when `claude` isn't on the PATH, accepts `-Detailed` in any position (and never passes it on to `claude`), and the PowerShell parse test declares its `[ref]` variables.
- **Settings hygiene.** `CONTENT_KEYS` covers all four launcher content flags plus `OTEL_LOG_RAW_API_BODIES`; a non-numeric `OTEL_METRIC_EXPORT_INTERVAL` is reported, not raised.
- **Collector validation.** `tests/smoke/test_validate.py` (tier 3) runs `otelcol validate` for all four overlay combinations, plus a negative case, instead of the manual loop in Task 3.
- **Preflight hardening.** Ports are validated (non-numeric, out-of-range and duplicate values are errors; empty means the Compose default); quoted `.env` values are read as Compose reads them; `DATA_DIR/out` is created with mode 700. `init-env.sh` sets `umask 077` before writing `.env`.
- **Scrub.** It also catches forward-slash and WSL-mounted Windows paths, macOS user paths, and the names of private projects.
- **Versions.** The collector image `0.140.0` reports binary version 0.140.1; the CHANGELOG says both.
- **Task 10** is generic migration guidance, not one user's cutover.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Dev tooling only (pytest, pyyaml, OTel SDK) |
| `.gitignore`, `.gitattributes`, `LICENSE` | Repo hygiene; MIT |
| `Makefile` | Entry points: `init`, `preflight`, `up`, `down`, `logs`, `verify`, `verify-settings`, `verify-claude` |
| `compose.yaml` | Services, profiles, ports, volumes |
| `.env.example` | Every configurable variable with public defaults |
| `collector/base.yaml`, `dual-env.yaml`, `openobserve.yaml`, `none.yaml` | Collector config and overlays |
| `scripts/init-env.sh` | Create `.env` with generated secrets, UID/GID and data dir; refuse to overwrite |
| `scripts/preflight.py` | Validate `.env`, overlays/profile consistency, free ports; create the data dir |
| `launchers/claude-traced.sh`, `launchers/claude-traced.ps1` | Per-launch content capture |
| `examples/user-settings.json`, `examples/project-settings.local.json` | Copy-paste settings |
| `tests/offline/` | Tier 1: graph, env coverage, examples, launchers, scrub, gitattributes |
| `tests/settings/` | Tier 2: settings hygiene + fixtures |
| `tests/smoke/` | Tier 3: Compose up per overlay combination + synthetic OTLP |
| `tests/claude/` | Tier 4: real `claude -p` tests (opt-in) |
| `docs/concepts.md`, `findings.md`, `dual-environment.md`, `pipelines.md` | Docs |
| `README.md`, `SECURITY.md`, `CHANGELOG.md` | Top-level docs |
| `.github/workflows/verify.yml` | CI: tiers 1 and 3 |

---

### Task 1: Repository skeleton, license, line endings, public-readiness scrub

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.gitattributes`, `LICENSE`, `tests/__init__.py`, `tests/offline/__init__.py`, `tests/offline/scrub.py`, `tests/offline/test_public_readiness.py`

**Interfaces:**
- Produces: `tests.offline.scrub.find_personal_data(text: str) -> list[str]` (the names of the pattern kinds found). `tests.offline.scrub.tracked_files(repo: Path) -> list[Path]`.

- [ ] **Step 1: Create `pyproject.toml`, `.gitignore`, `.gitattributes`, `LICENSE`**

`pyproject.toml`:
```toml
[project]
name = "claude-code-otel-local"
version = "0.1.0"
description = "Local, native-only observability for Claude Code's OpenTelemetry export"
requires-python = ">=3.11"
license = "MIT"
dependencies = []

[dependency-groups]
dev = [
  "pytest>=8",
  "pyyaml>=6",
  "opentelemetry-sdk>=1.30",
  "opentelemetry-exporter-otlp-proto-http>=1.30",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["docker: needs Docker (tier 3)", "claude: needs Claude Code CLI (tier 4)"]
```

`.gitignore`:
```gitignore
.env
data/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.claude/settings.local.json
```

`.gitattributes`:
```gitattributes
* text=auto
*.sh text eol=lf
*.py text eol=lf
*.yaml text eol=lf
*.yml text eol=lf
*.md text eol=lf
*.json text eol=lf
Makefile text eol=lf
*.ps1 text eol=crlf
```

`LICENSE`: the standard MIT license text with `Copyright (c) 2026` and the author's name.

- [ ] **Step 2: Write the failing tests**

`tests/offline/test_public_readiness.py`:
```python
from pathlib import Path

import pytest

from tests.offline.scrub import find_personal_data, tracked_files

REPO = Path(__file__).resolve().parents[2]


# Samples are assembled from pieces so this file (and the plan) never contains a literal match.
@pytest.mark.parametrize(
    "text,kind",
    [
        ("contact me at someone" + "@" + "mail.test.org", "email"),
        ("path /home" + "/alice/project", "home_path"),
        ("C:" + "\\Users\\" + "alice" + "\\.claude", "windows_user_path"),
        ("session " + "0a1b2c3d" + "-0000-4000-8000-" + "0123456789ab", "uuid"),
        ("key " + "sk-ant-" + "api03-abcdefghijklmnop", "token"),
        ("Authorization=" + "Basic " + "YWRtaW46c2VjcmV0cGFzc3dvcmQ=", "token"),
    ],
)
def test_detects_personal_data(text, kind):
    assert kind in find_personal_data(text)


@pytest.mark.parametrize(
    "text",
    [
        "admin@example.com",
        r"C:\Users\<user>\.claude\settings.json",
        "/home/<user>/project and ~/.claude/settings.json",
        "sha256:e61b2ec06fa1f2f96fb9ffbdf55a7484290931188f82b05393def69b85eeaba2",
        "Authorization=Basic <redacted>",
    ],
)
def test_allows_placeholders(text):
    assert find_personal_data(text) == []


def test_repository_has_no_personal_data():
    hits = {}
    for path in tracked_files(REPO):
        kinds = find_personal_data(path.read_text(encoding="utf-8", errors="replace"))
        if kinds:
            hits[str(path.relative_to(REPO))] = kinds
    assert not hits, f"personal data patterns found (kinds only): {hits}"


def test_gitattributes_line_endings():
    text = (REPO / ".gitattributes").read_text()
    assert "*.sh text eol=lf" in text
    assert "*.ps1 text eol=crlf" in text
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv sync && uv run pytest tests/offline/test_public_readiness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.offline.scrub'`

- [ ] **Step 4: Implement `tests/offline/scrub.py`**

```python
"""Detect personal data that must never ship in a public repo. Reports pattern kinds only."""

import re
import subprocess
from pathlib import Path

PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "home_path": re.compile(r"/home/(?!<user>|user\b|runner\b)[A-Za-z0-9_.-]+"),
    "windows_user_path": re.compile(r"C:\\Users\\(?!<user>|Public\b)[A-Za-z0-9_.-]+", re.IGNORECASE),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
    "token": re.compile(
        r"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|pk-lf-[A-Za-z0-9-]{10,}"
        r"|Basic [A-Za-z0-9+/]{16,}={0,2})"
    ),
}


def find_personal_data(text: str) -> list[str]:
    return sorted(kind for kind, pattern in PATTERNS.items() if pattern.search(text))


def tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    skip_suffixes = {".png", ".jpg", ".ico", ".lock"}
    return [repo / p for p in out if (repo / p).is_file() and Path(p).suffix not in skip_suffixes]
```
Create empty `tests/__init__.py` and `tests/offline/__init__.py`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/offline/test_public_readiness.py -v`
Expected: all PASS. `test_repository_has_no_personal_data` includes the committed spec and plan.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .gitattributes LICENSE tests/
git commit -m "chore: repo skeleton, MIT license, line endings, public-readiness scrub"
```

---

### Task 2: Collector configs and offline pipeline-graph validation

**Files:**
- Create: `collector/base.yaml`, `collector/dual-env.yaml`, `collector/openobserve.yaml`, `collector/none.yaml`, `tests/offline/collector_graph.py`, `tests/offline/test_collector_graph.py`

**Interfaces:**
- Produces:
  - `tests.offline.collector_graph.merge_configs(paths: list[Path]) -> dict`: maps merge deeply, lists are replaced (the collector's semantics).
  - `tests.offline.collector_graph.graph_errors(cfg: dict) -> list[str]`.
  - `tests.offline.collector_graph.COMBOS: list[tuple[str, str]]`.
  - Config component names used later: receivers `otlp/a`, `otlp/b`; fan-out pipelines `traces/out`, `metrics/out`, `logs/out`; exporter `otlphttp/openobserve`.

- [ ] **Step 1: Write the failing test**

`tests/offline/test_collector_graph.py`:
```python
from pathlib import Path

import pytest

from tests.offline.collector_graph import COMBOS, graph_errors, merge_configs

COLLECTOR = Path(__file__).resolve().parents[2] / "collector"


@pytest.mark.parametrize("o1,o2", COMBOS, ids=lambda x: x)
def test_every_combination_forms_a_valid_graph(o1, o2):
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / f"{o1}.yaml", COLLECTOR / f"{o2}.yaml"])
    assert graph_errors(cfg) == []


def test_openobserve_overlay_keeps_fanout_receivers():
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / "openobserve.yaml"])
    for p in ("metrics/out", "logs/out"):
        pipe = cfg["service"]["pipelines"][p]
        assert pipe["receivers"], p
        assert "otlphttp/openobserve" in pipe["exporters"], p
        assert any(e.startswith("file/") for e in pipe["exporters"]), p


def test_traces_go_to_phoenix_and_file_in_every_combo():
    for o1, o2 in COMBOS:
        cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / f"{o1}.yaml", COLLECTOR / f"{o2}.yaml"])
        assert set(cfg["service"]["pipelines"]["traces/out"]["exporters"]) >= {"file/traces", "otlphttp/phoenix"}


def test_every_env_pipeline_tags_the_environment():
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / "dual-env.yaml"])
    for name, pipe in cfg["service"]["pipelines"].items():
        if name.endswith(("/a", "/b")):
            procs = pipe["processors"]
            assert any(p.startswith("resource/") for p in procs), name
            if name.startswith("traces/"):
                assert any(p.startswith("attributes/") for p in procs), name


def test_graph_errors_catches_undefined_component():
    bad = {"receivers": {"otlp/a": {}}, "exporters": {}, "service": {"pipelines": {
        "traces/a": {"receivers": ["otlp/a"], "exporters": ["missing"]}}}}
    assert graph_errors(bad)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/offline/test_collector_graph.py -v`
Expected: FAIL (`No module named 'tests.offline.collector_graph'`)

- [ ] **Step 3: Implement `tests/offline/collector_graph.py`**

```python
"""Replicate the collector's multi --config merge (maps deep-merge, lists replace) and check the graph."""

from pathlib import Path

import yaml

COMBOS = [("none", "none"), ("dual-env", "none"), ("openobserve", "none"), ("dual-env", "openobserve")]
KINDS = ("receivers", "processors", "exporters", "connectors")


def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _merge(a[k], v) if k in a else v
        return out
    return b


def merge_configs(paths: list[Path]) -> dict:
    cfg: dict = {}
    for p in paths:
        cfg = _merge(cfg, yaml.safe_load(p.read_text()) or {})
    return cfg


def graph_errors(cfg: dict) -> list[str]:
    errors = []
    connectors = set(cfg.get("connectors") or {})
    pipelines = (cfg.get("service") or {}).get("pipelines") or {}
    if not pipelines:
        return ["no pipelines"]
    for name, pipe in pipelines.items():
        for role, kinds in (("receivers", ("receivers", "connectors")),
                            ("processors", ("processors",)),
                            ("exporters", ("exporters", "connectors"))):
            refs = pipe.get(role) or []
            if role != "processors" and not refs:
                errors.append(f"{name}: no {role}")
            for ref in refs:
                if not any(ref in (cfg.get(k) or {}) for k in kinds):
                    errors.append(f"{name}: undefined {role[:-1]} {ref}")
    for c in connectors:
        used_in = sum(c in (p.get("exporters") or []) for p in pipelines.values())
        used_out = sum(c in (p.get("receivers") or []) for p in pipelines.values())
        if not (used_in and used_out):
            errors.append(f"connector {c} must be both an exporter and a receiver")
    return errors
```

- [ ] **Step 4: Write the collector configs**

`collector/base.yaml`:
```yaml
# Single-environment default. Receiver A tags everything with ENV_A_NAME, then hands off to forward
# connectors; the fan-out pipelines own the sinks so overlays never need to edit env pipelines.
receivers:
  otlp/a:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}
  resource/a:
    attributes:
      - key: deployment.environment.name
        value: ${env:ENV_A_NAME}
        action: upsert
  # Phoenix discards resource attributes, so traces also carry the tag on every span.
  attributes/a:
    actions:
      - key: deployment.environment.name
        value: ${env:ENV_A_NAME}
        action: upsert

connectors:
  forward/traces: {}
  forward/metrics: {}
  forward/logs: {}

exporters:
  file/traces:
    path: /data/out/traces.jsonl
  file/metrics:
    path: /data/out/metrics.jsonl
  file/logs:
    path: /data/out/logs.jsonl
  otlphttp/phoenix:
    endpoint: http://phoenix:6006
    tls:
      insecure: true

service:
  pipelines:
    traces/a:
      receivers: [otlp/a]
      processors: [resource/a, attributes/a]
      exporters: [forward/traces]
    metrics/a:
      receivers: [otlp/a]
      processors: [resource/a]
      exporters: [forward/metrics]
    logs/a:
      receivers: [otlp/a]
      processors: [resource/a]
      exporters: [forward/logs]
    traces/out:
      receivers: [forward/traces]
      processors: [batch]
      exporters: [file/traces, otlphttp/phoenix]
    metrics/out:
      receivers: [forward/metrics]
      processors: [batch]
      exporters: [file/metrics]
    logs/out:
      receivers: [forward/logs]
      processors: [batch]
      exporters: [file/logs]
```

`collector/dual-env.yaml`:
```yaml
# Second environment (e.g. native Windows next to WSL): receiver B on 4320, tagged ENV_B_NAME.
# Adds new keys only; the fan-out pipelines in base.yaml are untouched.
receivers:
  otlp/b:
    protocols:
      http:
        endpoint: 0.0.0.0:4320

processors:
  resource/b:
    attributes:
      - key: deployment.environment.name
        value: ${env:ENV_B_NAME}
        action: upsert
  attributes/b:
    actions:
      - key: deployment.environment.name
        value: ${env:ENV_B_NAME}
        action: upsert

service:
  pipelines:
    traces/b:
      receivers: [otlp/b]
      processors: [resource/b, attributes/b]
      exporters: [forward/traces]
    metrics/b:
      receivers: [otlp/b]
      processors: [resource/b]
      exporters: [forward/metrics]
    logs/b:
      receivers: [otlp/b]
      processors: [resource/b]
      exporters: [forward/logs]
```

`collector/openobserve.yaml`:
```yaml
# Metrics and log events to OpenObserve (Compose profile "openobserve"). Replaces only the
# metrics/logs fan-out exporter lists, so it composes with any number of environments.
exporters:
  otlphttp/openobserve:
    endpoint: http://openobserve:5080/api/default
    headers:
      Authorization: Basic ${env:OPENOBSERVE_BASIC_AUTH}
    tls:
      insecure: true

service:
  pipelines:
    metrics/out:
      exporters: [file/metrics, otlphttp/openobserve]
    logs/out:
      exporters: [file/logs, otlphttp/openobserve]
```

`collector/none.yaml`:
```yaml
{}
```

- [ ] **Step 5: Run the tests to verify they pass, then validate with the real collector**

Run: `uv run pytest tests/offline/test_collector_graph.py -v`
Expected: all PASS.

Run the real validator for all four combinations:
```bash
for c in "none none" "dual-env none" "openobserve none" "dual-env openobserve"; do set -- $c
  docker run --rm -v "$PWD/collector:/etc/otelcol:ro" -e ENV_A_NAME=a -e ENV_B_NAME=b -e OPENOBSERVE_BASIC_AUTH=x \
    otel/opentelemetry-collector-contrib:0.140.0 validate \
    --config=/etc/otelcol/base.yaml --config=/etc/otelcol/$1.yaml --config=/etc/otelcol/$2.yaml \
    && echo "ok $1+$2"; done
```
Expected: `ok none+none`, `ok dual-env+none`, `ok openobserve+none`, `ok dual-env+openobserve`. This was checked against drafts of these configs on 2026-09-27.

- [ ] **Step 6: Commit**

```bash
git add collector/ tests/offline/collector_graph.py tests/offline/test_collector_graph.py
git commit -m "feat(collector): base config with forward fan-out, dual-env and openobserve overlays"
```

---

### Task 3: Compose, `.env.example`, init-env and preflight

**Files:**
- Create: `compose.yaml`, `.env.example`, `scripts/init-env.sh`, `scripts/preflight.py`, `Makefile`, `tests/offline/test_env_and_compose.py`, `tests/offline/test_preflight.py`, `tests/offline/test_init_env.py`

**Interfaces:**
- Consumes: the collector file names from Task 2.
- Produces:
  - `scripts/preflight.py` with `parse_env(text: str) -> dict[str, str]`, `check_env(env: dict[str, str], collector_dir: Path) -> list[str]`, `check_ports(env: dict[str, str], is_free: Callable[[int], bool]) -> list[str]`, `active_ports(env: dict[str, str]) -> dict[str, int]`, `main(argv: list[str]) -> int` (`--skip-ports` flag).
  - `.env` keys: all from spec §3.1, plus `HOST_UID`, `HOST_GID`, `DATA_DIR`, `COMPOSE_PROFILES`, `COMPOSE_PROJECT_NAME`.
  - Make targets: `init`, `preflight`, `up`, `down`, `logs`.

- [ ] **Step 1: Write the failing tests**

`tests/offline/test_preflight.py`:
```python
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", REPO / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

GOOD = {
    "ENV_A_NAME": "local", "ENV_A_PORT": "4318", "ENV_B_NAME": "windows", "ENV_B_PORT": "4320",
    "COLLECTOR_OVERLAY_1": "none", "COLLECTOR_OVERLAY_2": "none", "COMPOSE_PROFILES": "",
    "PHOENIX_PORT": "6006", "PHOENIX_DB_PASSWORD": "x" * 24, "HOST_UID": "1000", "HOST_GID": "1000",
    "DATA_DIR": "./data", "OPENOBSERVE_PORT": "5080", "OPENOBSERVE_ROOT_EMAIL": "admin@example.com",
    "OPENOBSERVE_ROOT_PASSWORD": "y" * 24, "OPENOBSERVE_BASIC_AUTH": "z" * 32,
}


def test_parse_env_ignores_comments_and_blank_lines():
    env = preflight.parse_env("# c\n\nA=1\nB = two # trailing\nC=\n")
    assert env == {"A": "1", "B": "two", "C": ""}


def test_good_env_passes():
    assert preflight.check_env(dict(GOOD), REPO / "collector") == []


def test_check_env_requires_secrets():
    env = dict(GOOD, PHOENIX_DB_PASSWORD="", HOST_UID="")
    errors = preflight.check_env(env, REPO / "collector")
    assert any("PHOENIX_DB_PASSWORD" in e for e in errors)
    assert any("HOST_UID" in e for e in errors)
    assert any("init-env.sh" in e for e in errors)


def test_check_env_rejects_unknown_overlay():
    errors = preflight.check_env(dict(GOOD, COLLECTOR_OVERLAY_1="dualenv"), REPO / "collector")
    assert any("dualenv" in e for e in errors)


def test_check_env_openobserve_overlay_requires_profile():
    errors = preflight.check_env(dict(GOOD, COLLECTOR_OVERLAY_2="openobserve"), REPO / "collector")
    assert any("COMPOSE_PROFILES" in e for e in errors)
    errors = preflight.check_env(dict(GOOD, COMPOSE_PROFILES="openobserve"), REPO / "collector")
    assert any("COLLECTOR_OVERLAY" in e for e in errors)


def test_active_ports_follow_mode():
    assert set(preflight.active_ports(dict(GOOD))) == {"ENV_A_PORT", "PHOENIX_PORT"}
    full = dict(GOOD, COLLECTOR_OVERLAY_1="dual-env", COLLECTOR_OVERLAY_2="openobserve", COMPOSE_PROFILES="openobserve")
    assert set(preflight.active_ports(full)) == {"ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT", "OPENOBSERVE_PORT"}


def test_check_ports_reports_busy_port():
    errors = preflight.check_ports(dict(GOOD), is_free=lambda port: port != 6006)
    assert errors == ["port 6006 (PHOENIX_PORT) is already in use on 127.0.0.1; change it in .env or stop the other service"]
```

`tests/offline/test_env_and_compose.py`:
```python
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VAR = re.compile(r"\$\{(?:env:)?([A-Z_][A-Z0-9_]*)")


def referenced_vars() -> set[str]:
    names = set()
    for p in [REPO / "compose.yaml", *sorted((REPO / "collector").glob("*.yaml"))]:
        names |= set(VAR.findall(p.read_text()))
    return names


def example_keys() -> set[str]:
    keys = set()
    for line in (REPO / ".env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_covers_every_variable():
    missing = referenced_vars() - example_keys()
    assert not missing, f".env.example lacks: {sorted(missing)}"


def test_compose_requires_db_password():
    assert "${PHOENIX_DB_PASSWORD:?" in (REPO / "compose.yaml").read_text()


def test_published_ports_bind_localhost():
    text = (REPO / "compose.yaml").read_text()
    ports = re.findall(r'-\s*"([^"]+:\d+)"', text)
    assert ports and all(p.startswith("127.0.0.1:") for p in ports), ports


def test_images_are_pinned():
    text = (REPO / "compose.yaml").read_text()
    for image in re.findall(r"image:\s*(\S+)", text):
        assert "@sha256:" in image or re.search(r":\d[\w.-]*$", image), image
        assert not image.endswith(":latest"), image
```

`tests/offline/test_init_env.py`:
```python
import base64
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run_init(tmp_path: Path) -> subprocess.CompletedProcess:
    shutil.copy(REPO / ".env.example", tmp_path / ".env.example")
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "init-env.sh", tmp_path / "scripts" / "init-env.sh")
    return subprocess.run(["bash", "scripts/init-env.sh"], cwd=tmp_path, capture_output=True, text=True)


def read_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_init_env_generates_secrets_and_basic_auth(tmp_path):
    assert run_init(tmp_path).returncode == 0
    env = read_env(tmp_path / ".env")
    assert len(env["PHOENIX_DB_PASSWORD"]) >= 24
    assert len(env["OPENOBSERVE_ROOT_PASSWORD"]) >= 24
    expected = base64.b64encode(f'{env["OPENOBSERVE_ROOT_EMAIL"]}:{env["OPENOBSERVE_ROOT_PASSWORD"]}'.encode()).decode()
    assert env["OPENOBSERVE_BASIC_AUTH"] == expected


def test_init_env_writes_uid_gid_and_data_dir(tmp_path):
    run_init(tmp_path)
    env = read_env(tmp_path / ".env")
    assert env["HOST_UID"].isdigit() and env["HOST_GID"].isdigit()
    assert (tmp_path / "data" / "out").is_dir()


def test_init_env_refuses_to_overwrite(tmp_path):
    run_init(tmp_path)
    second = subprocess.run(["bash", "scripts/init-env.sh"], cwd=tmp_path, capture_output=True, text=True)
    assert second.returncode != 0
    assert "already exists" in second.stderr
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/offline/test_preflight.py tests/offline/test_env_and_compose.py tests/offline/test_init_env.py -v`
Expected: FAIL (missing `scripts/preflight.py`, `compose.yaml`, `.env.example`, `scripts/init-env.sh`)

- [ ] **Step 3: Write `.env.example`**

```ini
# Copy with scripts/init-env.sh (generates secrets, UID/GID, data dir). Never commit .env.
COMPOSE_PROJECT_NAME=claude-code-otel-local
# Add "openobserve" here AND set an overlay slot to openobserve to enable OpenObserve.
COMPOSE_PROFILES=

# Receiver A (always on) and its environment tag.
ENV_A_NAME=local
ENV_A_PORT=4318
# Receiver B (only with COLLECTOR_OVERLAY_*=dual-env), e.g. native Windows next to WSL.
ENV_B_NAME=windows
ENV_B_PORT=4320

# Collector overlays: none | dual-env | openobserve
COLLECTOR_OVERLAY_1=none
COLLECTOR_OVERLAY_2=none

PHOENIX_PORT=6006
PHOENIX_RETENTION_DAYS=14
PHOENIX_DB_PASSWORD=

OPENOBSERVE_PORT=5080
OPENOBSERVE_ROOT_EMAIL=admin@example.com
OPENOBSERVE_ROOT_PASSWORD=
OPENOBSERVE_BASIC_AUTH=
OPENOBSERVE_RETENTION_DAYS=30

# Written by init-env.sh so the collector can write to the bind-mounted data dir.
HOST_UID=
HOST_GID=
DATA_DIR=./data
```

- [ ] **Step 4: Write `compose.yaml`**

```yaml
name: ${COMPOSE_PROJECT_NAME:-claude-code-otel-local}

x-logging: &logging
  driver: local
  options:
    max-size: "10m"
    max-file: "3"

services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.140.0
    restart: unless-stopped
    user: "${HOST_UID:-1000}:${HOST_GID:-1000}"
    command:
      - --config=/etc/otelcol/base.yaml
      - --config=/etc/otelcol/${COLLECTOR_OVERLAY_1:-none}.yaml
      - --config=/etc/otelcol/${COLLECTOR_OVERLAY_2:-none}.yaml
    environment:
      ENV_A_NAME: ${ENV_A_NAME:-local}
      ENV_B_NAME: ${ENV_B_NAME:-windows}
      OPENOBSERVE_BASIC_AUTH: ${OPENOBSERVE_BASIC_AUTH:-}
    volumes:
      - ./collector:/etc/otelcol:ro
      - ${DATA_DIR:-./data}/out:/data/out
    ports:
      - "127.0.0.1:${ENV_A_PORT:-4318}:4318"
      - "127.0.0.1:${ENV_B_PORT:-4320}:4320"
    depends_on:
      phoenix:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 256m
    logging: *logging

  phoenix-db:
    image: postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
    restart: unless-stopped
    environment:
      POSTGRES_USER: phoenix
      POSTGRES_PASSWORD: ${PHOENIX_DB_PASSWORD:?run scripts/init-env.sh first}
      POSTGRES_DB: phoenix
    volumes:
      - phoenix-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U phoenix -d phoenix"]
      interval: 3s
      timeout: 3s
      retries: 20
    deploy:
      resources:
        limits:
          memory: 512m
    logging: *logging

  phoenix:
    image: arizephoenix/phoenix@sha256:e61b2ec06fa1f2f96fb9ffbdf55a7484290931188f82b05393def69b85eeaba2
    restart: unless-stopped
    depends_on:
      phoenix-db:
        condition: service_healthy
    environment:
      PHOENIX_SQL_DATABASE_URL: postgresql://phoenix:${PHOENIX_DB_PASSWORD:?run scripts/init-env.sh first}@phoenix-db:5432/phoenix
      PHOENIX_DEFAULT_RETENTION_POLICY_DAYS: ${PHOENIX_RETENTION_DAYS:-14}
      PHOENIX_TELEMETRY_ENABLED: "false"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:6006/healthz')"]
      interval: 5s
      timeout: 5s
      retries: 30
    ports:
      - "127.0.0.1:${PHOENIX_PORT:-6006}:6006"
    deploy:
      resources:
        limits:
          memory: 1g
    logging: *logging

  openobserve:
    profiles: [openobserve]
    image: public.ecr.aws/zinclabs/openobserve@sha256:e1ff0445fab3e748ac4cf630308cc8493579e50d19ad255bb3a3b8c1b710aaf7
    restart: unless-stopped
    environment:
      ZO_ROOT_USER_EMAIL: ${OPENOBSERVE_ROOT_EMAIL:-admin@example.com}
      ZO_ROOT_USER_PASSWORD: ${OPENOBSERVE_ROOT_PASSWORD:-}
      ZO_DATA_DIR: /data
      ZO_COMPACT_DATA_RETENTION_DAYS: ${OPENOBSERVE_RETENTION_DAYS:-30}
    volumes:
      - openobserve-data:/data
    ports:
      - "127.0.0.1:${OPENOBSERVE_PORT:-5080}:5080"
    deploy:
      resources:
        limits:
          memory: 1g
    logging: *logging

volumes:
  phoenix-db-data:
  openobserve-data:
```

- [ ] **Step 5: Write `scripts/init-env.sh`**

```bash
#!/usr/bin/env bash
# Create .env from .env.example with generated secrets, this user's UID/GID, and the data dir.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env already exists; edit it or delete it first" >&2
  exit 1
fi

rand() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
db_pw=$(rand)
oo_pw=$(rand)
oo_email=$(grep -E '^OPENOBSERVE_ROOT_EMAIL=' .env.example | cut -d= -f2-)
oo_auth=$(printf '%s:%s' "$oo_email" "$oo_pw" | base64 | tr -d '\n')

sed -e "s|^PHOENIX_DB_PASSWORD=.*|PHOENIX_DB_PASSWORD=${db_pw}|" \
    -e "s|^OPENOBSERVE_ROOT_PASSWORD=.*|OPENOBSERVE_ROOT_PASSWORD=${oo_pw}|" \
    -e "s|^OPENOBSERVE_BASIC_AUTH=.*|OPENOBSERVE_BASIC_AUTH=${oo_auth}|" \
    -e "s|^HOST_UID=.*|HOST_UID=$(id -u)|" \
    -e "s|^HOST_GID=.*|HOST_GID=$(id -g)|" \
    .env.example > .env
chmod 600 .env
mkdir -p data/out
echo "wrote .env (mode 600) and created data/out"
```
Run `chmod +x scripts/init-env.sh`.

- [ ] **Step 6: Write `scripts/preflight.py`**

```python
#!/usr/bin/env python3
"""Check .env before `docker compose up`: secrets, overlay/profile consistency, free ports, data dir."""

import socket
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
REQUIRED = ("PHOENIX_DB_PASSWORD", "HOST_UID", "HOST_GID")


def parse_env(text: str) -> dict[str, str]:
    env = {}
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _overlays(env: dict[str, str]) -> list[str]:
    return [env.get(k, "none") or "none" for k in ("COLLECTOR_OVERLAY_1", "COLLECTOR_OVERLAY_2")]


def _profiles(env: dict[str, str]) -> set[str]:
    return {p.strip() for p in env.get("COMPOSE_PROFILES", "").split(",") if p.strip()}


def check_env(env: dict[str, str], collector_dir: Path) -> list[str]:
    errors = [f"{k} is empty; run scripts/init-env.sh" for k in REQUIRED if not env.get(k)]
    overlays = _overlays(env)
    for name in overlays:
        if not (collector_dir / f"{name}.yaml").is_file():
            errors.append(f"unknown collector overlay '{name}' (expected none, dual-env or openobserve)")
    real = [o for o in overlays if o != "none"]
    if len(real) != len(set(real)):
        errors.append("COLLECTOR_OVERLAY_1 and COLLECTOR_OVERLAY_2 name the same overlay")
    oo_overlay, oo_profile = "openobserve" in overlays, "openobserve" in _profiles(env)
    if oo_overlay and not oo_profile:
        errors.append("openobserve overlay is set but COMPOSE_PROFILES does not include openobserve")
    if oo_profile and not oo_overlay:
        errors.append("COMPOSE_PROFILES includes openobserve but no COLLECTOR_OVERLAY_* is openobserve")
    if oo_overlay:
        for k in ("OPENOBSERVE_ROOT_PASSWORD", "OPENOBSERVE_BASIC_AUTH"):
            if not env.get(k):
                errors.append(f"{k} is empty; run scripts/init-env.sh")
    return errors


def active_ports(env: dict[str, str]) -> dict[str, int]:
    ports = {"ENV_A_PORT": int(env.get("ENV_A_PORT", 4318)), "PHOENIX_PORT": int(env.get("PHOENIX_PORT", 6006))}
    if "dual-env" in _overlays(env):
        ports["ENV_B_PORT"] = int(env.get("ENV_B_PORT", 4320))
    if "openobserve" in _profiles(env):
        ports["OPENOBSERVE_PORT"] = int(env.get("OPENOBSERVE_PORT", 5080))
    return ports


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def check_ports(env: dict[str, str], is_free: Callable[[int], bool] = _is_free) -> list[str]:
    return [
        f"port {port} ({name}) is already in use on 127.0.0.1; change it in .env or stop the other service"
        for name, port in active_ports(env).items()
        if not is_free(port)
    ]


def main(argv: list[str]) -> int:
    env_path = REPO / ".env"
    if not env_path.is_file():
        print("no .env; run scripts/init-env.sh", file=sys.stderr)
        return 1
    env = parse_env(env_path.read_text())
    errors = check_env(env, REPO / "collector")
    if "--skip-ports" not in argv:
        errors += check_ports(env)
    (REPO / env.get("DATA_DIR", "./data") / "out").mkdir(parents=True, exist_ok=True)
    for e in errors:
        print(f"preflight: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 7: Write the `Makefile`** (the verify targets are completed in Task 8)

```makefile
.PHONY: init preflight up down logs verify verify-settings verify-claude

init:
	bash scripts/init-env.sh

# Skip the port check when this project's containers are already running (they hold the ports).
preflight:
	@if [ -n "$$(docker compose ps -q --status running 2>/dev/null)" ]; then \
	  python3 scripts/preflight.py --skip-ports; else python3 scripts/preflight.py; fi

up: preflight
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f otel-collector
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/offline -v`
Expected: all PASS.

Then: `docker compose --env-file .env.example config -q`
Expected: exits non-zero with `run scripts/init-env.sh first`. That's the required-password guard working.

- [ ] **Step 9: Commit**

```bash
git add compose.yaml .env.example scripts/ Makefile tests/offline/
git commit -m "feat: compose stack, env template, init-env and preflight checks"
```

---

### Task 4: Tier 3, Docker smoke test with synthetic OTLP

**Files:**
- Create: `tests/smoke/__init__.py`, `tests/smoke/otlp_send.py`, `tests/smoke/stack.py`, `tests/smoke/test_smoke.py`

**Interfaces:**
- Consumes: `compose.yaml`, `.env.example` keys, `collector/*.yaml` from Tasks 2–3; `COMBOS` from `tests.offline.collector_graph`.
- Produces:
  - `tests.smoke.otlp_send.send(port: int, marker: str) -> None`: one span `smoke.span`, one log record and one counter, each carrying attribute `smoke.id=<marker>`.
  - `tests.smoke.stack.Stack`, a context manager: `Stack(overlay_1: str, overlay_2: str, tmp_path: Path)` with `.ports: dict[str,int]`, `.data_dir: Path`, `.env: dict[str,str]`, `.psql(sql: str) -> str`, `.openobserve_search(marker: str) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/smoke/test_smoke.py`:
```python
import json
import time

import pytest

from tests.offline.collector_graph import COMBOS
from tests.smoke.otlp_send import send
from tests.smoke.stack import Stack

pytestmark = pytest.mark.docker


def jsonl_records(path, marker):
    """Return (resource_attrs, item_attrs) for every record whose attributes carry the marker."""
    found = []
    if not path.exists():
        return found
    for line in path.read_text().splitlines():
        batch = json.loads(line)
        for key, scope_key, items_key in (("resourceSpans", "scopeSpans", "spans"),
                                          ("resourceLogs", "scopeLogs", "logRecords"),
                                          ("resourceMetrics", "scopeMetrics", "metrics")):
            for res in batch.get(key, []):
                rattrs = {a["key"]: next(iter(a["value"].values())) for a in res["resource"].get("attributes", [])}
                for scope in res.get(scope_key, []):
                    for item in scope.get(items_key, []):
                        if marker in json.dumps(item):
                            attrs = {a["key"]: next(iter(a["value"].values())) for a in item.get("attributes", [])}
                            found.append((rattrs, attrs))
    return found


def wait_for(fn, timeout=60, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    return fn()


@pytest.mark.parametrize("o1,o2", COMBOS, ids=lambda x: x)
def test_stack_tags_and_routes_every_signal(o1, o2, tmp_path):
    with Stack(o1, o2, tmp_path) as stack:
        receivers = [("ENV_A_PORT", stack.env["ENV_A_NAME"])]
        if "dual-env" in (o1, o2):
            receivers.append(("ENV_B_PORT", stack.env["ENV_B_NAME"]))
        for port_key, env_name in receivers:
            marker = f"smoke-{env_name}-{int(time.time())}"
            send(stack.ports[port_key], marker)
            out = stack.data_dir / "out"
            for signal in ("traces", "logs", "metrics"):
                recs = wait_for(lambda: jsonl_records(out / f"{signal}.jsonl", marker))
                assert recs, f"{signal} for {env_name} not written"
                assert all(r[0].get("deployment.environment.name") == env_name for r in recs), signal
            span_env = wait_for(lambda: stack.psql(
                "select attributes->'deployment'->'environment'->>'name' from spans "
                f"where name='smoke.span' and attributes->'smoke'->>'id'='{marker}'"))
            assert span_env == env_name, "Phoenix span missing the environment tag as a span attribute"
            if "openobserve" in (o1, o2):
                assert wait_for(lambda: stack.openobserve_search(marker), timeout=90) > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/smoke -v -m docker`
Expected: FAIL (`No module named 'tests.smoke.otlp_send'`)

- [ ] **Step 3: Implement `tests/smoke/otlp_send.py`**

```python
"""Send one span, one log record and one metric over OTLP/HTTP, each tagged smoke.id=<marker>."""

import logging

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def send(port: int, marker: str) -> None:
    base = f"http://127.0.0.1:{port}"
    resource = Resource.create({"service.name": "claude-code-otel-local-smoke"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
    with tracer_provider.get_tracer("smoke").start_as_current_span("smoke.span") as span:
        span.set_attribute("smoke.id", marker)
    tracer_provider.shutdown()

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs")))
    logger = logging.getLogger(f"smoke.{marker}")
    logger.propagate = False
    logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    logger.warning("smoke log %s", marker, extra={"smoke.id": marker})
    logger_provider.shutdown()

    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"), export_interval_millis=500)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    meter_provider.get_meter("smoke").create_counter("smoke.count").add(1, {"smoke.id": marker})
    meter_provider.shutdown()
```

- [ ] **Step 4: Implement `tests/smoke/stack.py`**

```python
"""Bring up an isolated copy of the stack (own project name, random ports, temp data dir)."""

import base64
import json
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Stack:
    def __init__(self, overlay_1: str, overlay_2: str, tmp_path: Path):
        self.data_dir = tmp_path / "data"
        (self.data_dir / "out").mkdir(parents=True)
        email, pw = "admin@example.com", secrets.token_urlsafe(24)
        self.ports = {k: _free_port() for k in ("ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT", "OPENOBSERVE_PORT")}
        uses_oo = "openobserve" in (overlay_1, overlay_2)
        self.env = {
            "COMPOSE_PROJECT_NAME": f"ccol-smoke-{secrets.token_hex(4)}",
            "COMPOSE_PROFILES": "openobserve" if uses_oo else "",
            "ENV_A_NAME": "envA", "ENV_B_NAME": "envB",
            "COLLECTOR_OVERLAY_1": overlay_1, "COLLECTOR_OVERLAY_2": overlay_2,
            "PHOENIX_DB_PASSWORD": secrets.token_urlsafe(24), "PHOENIX_RETENTION_DAYS": "1",
            "OPENOBSERVE_ROOT_EMAIL": email, "OPENOBSERVE_ROOT_PASSWORD": pw,
            "OPENOBSERVE_BASIC_AUTH": base64.b64encode(f"{email}:{pw}".encode()).decode(),
            "OPENOBSERVE_RETENTION_DAYS": "1",
            "HOST_UID": str(subprocess.check_output(["id", "-u"], text=True).strip()),
            "HOST_GID": str(subprocess.check_output(["id", "-g"], text=True).strip()),
            "DATA_DIR": str(self.data_dir),
            **{k: str(v) for k, v in self.ports.items()},
        }
        self.env_file = tmp_path / ".env"
        self.env_file.write_text("".join(f"{k}={v}\n" for k, v in self.env.items()))

    def _compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", "--env-file", str(self.env_file), *args],
                              cwd=REPO, capture_output=True, text=True, check=check)

    def __enter__(self):
        self._compose("up", "-d", "--wait", "--wait-timeout", "180")
        self._wait_port(self.ports["ENV_A_PORT"])
        return self

    def __exit__(self, *exc):
        self._compose("down", "-v", check=False)

    @staticmethod
    def _wait_port(port: int, timeout: float = 60) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return
            time.sleep(1)
        raise TimeoutError(f"port {port} never opened")

    def psql(self, sql: str) -> str:
        out = self._compose("exec", "-T", "phoenix-db", "psql", "-U", "phoenix", "-d", "phoenix", "-Atc", sql, check=False)
        return out.stdout.strip()

    def openobserve_search(self, marker: str) -> int:
        now = int(time.time() * 1_000_000)
        body = json.dumps({"query": {"sql": f"SELECT * FROM \"default\" WHERE str_match(body, '{marker}')",
                                     "start_time": now - 900_000_000, "end_time": now, "from": 0, "size": 10}}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.ports['OPENOBSERVE_PORT']}/api/default/_search", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Basic {self.env['OPENOBSERVE_BASIC_AUTH']}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return len(json.load(resp).get("hits", []))
        except OSError:
            return 0
```
Create an empty `tests/smoke/__init__.py`.

`--wait` covers only services with healthchecks (phoenix-db, phoenix). The collector port is polled by `_wait_port`, and OpenObserve search is retried by `wait_for`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/smoke -v -m docker`
Expected: 4 PASS (one per overlay combination), a few minutes in total.

If the `openobserve` case fails on the search, check `docker compose logs openobserve` for the stream name. OTLP logs land in stream `default` of org `default`. Adjust the SQL stream name only if the logs show otherwise.

- [ ] **Step 6: Commit**

```bash
git add tests/smoke/
git commit -m "test(smoke): per-combination compose run with synthetic OTLP, tag and routing asserts"
```

---

### Task 5: Launchers and examples, with offline tests

**Files:**
- Create: `launchers/claude-traced.sh`, `launchers/claude-traced.ps1`, `examples/user-settings.json`, `examples/project-settings.local.json`, `tests/offline/test_launchers.py`, `tests/offline/test_examples.py`

**Interfaces:**
- Produces:
  - `launchers/claude-traced.sh [claude args...]`, honoring `DETAILED=1`.
  - `launchers/claude-traced.ps1 [-Detailed] [claude args...]`.
  - Both add `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT` = `1`. Detailed mode adds `ENABLE_BETA_TRACING_DETAILED=1` and `BETA_TRACING_ENDPOINT` = `$OTEL_EXPORTER_OTLP_ENDPOINT` or `http://localhost:4318`.
  - `examples/user-settings.json` is `{"env": {...baseline...}}`.

- [ ] **Step 1: Write the failing tests**

`tests/offline/test_launchers.py`:
```python
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SH = REPO / "launchers" / "claude-traced.sh"
CONTENT = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_ASSISTANT_RESPONSES", "OTEL_LOG_TOOL_DETAILS", "OTEL_LOG_TOOL_CONTENT")


def fake_claude(tmp_path: Path) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text('#!/usr/bin/env bash\nenv | grep -E "^(OTEL_|ENABLE_BETA|BETA_TRACING)" | sort\necho "ARGS:$*"\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OTEL_", "ENABLE_BETA", "BETA_TRACING"))}
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return env


def run(env: dict, *args: str) -> str:
    return subprocess.run(["bash", str(SH), *args], env=env, capture_output=True, text=True, check=True).stdout


def test_sh_syntax():
    subprocess.run(["bash", "-n", str(SH)], check=True)


def test_sh_sets_content_flags_and_passes_args(tmp_path):
    out = run(fake_claude(tmp_path), "-p", "hello world")
    for key in CONTENT:
        assert f"{key}=1" in out
    assert "ENABLE_BETA_TRACING_DETAILED" not in out
    assert "ARGS:-p hello world" in out


def test_sh_detailed_uses_configured_endpoint(tmp_path):
    env = fake_claude(tmp_path) | {"DETAILED": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4320"}
    out = run(env, "-p", "x")
    assert "ENABLE_BETA_TRACING_DETAILED=1" in out
    assert "BETA_TRACING_ENDPOINT=http://localhost:4320" in out


def test_sh_detailed_defaults_endpoint(tmp_path):
    out = run(fake_claude(tmp_path) | {"DETAILED": "1"}, "-p", "x")
    assert "BETA_TRACING_ENDPOINT=http://localhost:4318" in out


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
def test_ps1_parses():
    script = REPO / "launchers" / "claude-traced.ps1"
    cmd = f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$e); if ($e) {{ exit 1 }}"
    subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], check=True)
```

`tests/offline/test_examples.py`:
```python
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
}


def test_user_settings_example_is_the_baseline():
    env = json.loads((REPO / "examples" / "user-settings.json").read_text())["env"]
    assert env == BASELINE


def test_user_settings_example_has_no_content_or_headers():
    env = json.loads((REPO / "examples" / "user-settings.json").read_text())["env"]
    assert not [k for k in env if k.startswith("OTEL_LOG_") or "HEADERS" in k or k == "OTEL_RESOURCE_ATTRIBUTES"]


def test_project_example_uses_only_allowed_keys():
    data = json.loads((REPO / "examples" / "project-settings.local.json").read_text())
    assert {e["serverName"] for e in data["deniedMcpServers"]} >= {"claude.ai Gmail"}
    for key, value in data.get("env", {}).items():
        assert key.endswith("_EXPORTER") and value == "none", key
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/offline/test_launchers.py tests/offline/test_examples.py -v`
Expected: FAIL (missing files)

- [ ] **Step 3: Write the launchers**

`launchers/claude-traced.sh`:
```bash
#!/usr/bin/env bash
# Launch Claude Code with telemetry *content* capture for this launch only.
#   launchers/claude-traced.sh                 # interactive, content on
#   launchers/claude-traced.sh -p "prompt"     # headless
#   DETAILED=1 launchers/claude-traced.sh -p … # + response text on spans (headless; interactive
#                                              #   sessions need org allowlisting per Claude Code docs)
# Works because user settings leave these keys unset (user settings win over the shell for keys
# they do set). Captured text is stored in plain text, including anything the agent reads.
set -euo pipefail

export OTEL_LOG_USER_PROMPTS=1
export OTEL_LOG_ASSISTANT_RESPONSES=1
export OTEL_LOG_TOOL_DETAILS=1
export OTEL_LOG_TOOL_CONTENT=1

if [[ "${DETAILED:-0}" == "1" ]]; then
  export ENABLE_BETA_TRACING_DETAILED=1
  export BETA_TRACING_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4318}"
fi

exec claude "$@"
```

`launchers/claude-traced.ps1`:
```powershell
<#
.SYNOPSIS
  Launch Claude Code (Windows) with telemetry content capture for this launch only.
.DESCRIPTION
  Sets the four OTEL_LOG_* content flags; -Detailed also sets ENABLE_BETA_TRACING_DETAILED and
  BETA_TRACING_ENDPOINT (from OTEL_EXPORTER_OTLP_ENDPOINT, else http://localhost:4318). Previous values
  are restored on exit. Arguments pass straight through via $args: a param() block with [Parameter]
  attributes would make PowerShell treat claude's -p as ambiguous with its common parameters.
.EXAMPLE
  pwsh -File .\launchers\claude-traced.ps1 -Detailed -p "prompt"
#>
$ClaudeArgs = @($args)
$Detailed = $false
if ($ClaudeArgs.Count -gt 0 -and $ClaudeArgs[0] -eq '-Detailed') {
  $Detailed = $true
  $ClaudeArgs = @($ClaudeArgs | Select-Object -Skip 1)
}

$vars = [ordered]@{
  OTEL_LOG_USER_PROMPTS        = '1'
  OTEL_LOG_ASSISTANT_RESPONSES = '1'
  OTEL_LOG_TOOL_DETAILS        = '1'
  OTEL_LOG_TOOL_CONTENT        = '1'
}
if ($Detailed) {
  $endpoint = [Environment]::GetEnvironmentVariable('OTEL_EXPORTER_OTLP_ENDPOINT', 'Process')
  if (-not $endpoint) { $endpoint = 'http://localhost:4318' }
  $vars['ENABLE_BETA_TRACING_DETAILED'] = '1'
  $vars['BETA_TRACING_ENDPOINT'] = $endpoint
}

$previous = @{}
foreach ($name in $vars.Keys) {
  $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
  [Environment]::SetEnvironmentVariable($name, $vars[$name], 'Process')
}
try {
  & claude @ClaudeArgs
  exit $LASTEXITCODE
}
finally {
  foreach ($name in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
  }
}
```

The PowerShell launcher reads `OTEL_EXPORTER_OTLP_ENDPOINT` from the process env only. Claude Code applies the settings `env` block inside its own process, so from a plain shell that value is usually unset. Dual-env users on Windows therefore set it in their shell profile to `http://localhost:4320`, or accept the default and edit it. `docs/dual-environment.md` (Task 7) documents this.

- [ ] **Step 4: Write the examples**

`examples/user-settings.json`:
```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"
  }
}
```

`examples/project-settings.local.json`:
```json
{
  "deniedMcpServers": [
    {"serverName": "claude.ai Gmail"},
    {"serverName": "claude.ai Canva"}
  ],
  "env": {
    "OTEL_TRACES_EXPORTER": "none",
    "OTEL_METRICS_EXPORTER": "none",
    "OTEL_LOGS_EXPORTER": "none"
  }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `chmod +x launchers/claude-traced.sh && uv run pytest tests/offline -v`
Expected: all PASS (`test_ps1_parses` skips if `pwsh` is absent).

- [ ] **Step 6: Commit**

```bash
git add launchers/ examples/ tests/offline/test_launchers.py tests/offline/test_examples.py
git commit -m "feat: per-launch content launchers and example settings"
```

---

### Task 6: Tiers 2 and 4, settings hygiene and Claude CLI tests (ported, de-personalized)

**Files:**
- Create: `tests/settings/__init__.py`, `tests/settings/keys.py`, `tests/settings/conftest.py`, `tests/settings/test_hygiene.py`, `tests/settings/fixtures/old-baseline.json`, `tests/settings/fixtures/good-baseline.json`, `tests/claude/__init__.py`, `tests/claude/conftest.py`, `tests/claude/test_precedence.py`, `tests/claude/test_end_to_end.py`

**Interfaces:**
- Consumes: the `BASELINE` values from Task 5; `.env` keys from Task 3.
- Produces:
  - Tier 2: environment variables `CLAUDE_SETTINGS_A` (default `~/.claude/settings.json`), `CLAUDE_SETTINGS_B` (optional), `CLAUDE_ENDPOINT_A` (default `http://localhost:4318`), `CLAUDE_ENDPOINT_B` (default `http://localhost:4320`).
  - Tier 4 is gated on `RUN_CLAUDE_CLI=1`.

- [ ] **Step 1: Write the fixtures**

`tests/settings/fixtures/good-baseline.json`: the same content as `examples/user-settings.json`.

`tests/settings/fixtures/old-baseline.json` (sanitized; the header value is a placeholder):
```json
{
  "env": {
    "PHOENIX_ENDPOINT": "http://localhost:6006",
    "ARIZE_TRACE_ENABLED": "true",
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://localhost:5080/api/default/v1/metrics",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://localhost:5080/api/default/v1/logs",
    "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <redacted>",
    "OTEL_LOG_USER_PROMPTS": "1",
    "OTEL_METRIC_EXPORT_INTERVAL": "5000",
    "OTEL_LOGS_EXPORT_INTERVAL": "5000"
  },
  "extraKnownMarketplaces": {"langfuse-observability": {}}
}
```

- [ ] **Step 2: Write the failing tests**

`tests/settings/keys.py`:
```python
BASELINE = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
}
CONTENT_KEYS = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_ASSISTANT_RESPONSES", "OTEL_LOG_TOOL_DETAILS",
                "OTEL_LOG_TOOL_CONTENT", "OTEL_LOG_RAW_API_BODIES")
PER_LAUNCH_KEYS = ("OTEL_RESOURCE_ATTRIBUTES", "ENABLE_BETA_TRACING_DETAILED", "BETA_TRACING_ENDPOINT")
VENDOR_ENV_PREFIXES = ("ARIZE_", "PHOENIX_", "LANGFUSE_", "CC_LANGFUSE_")
VENDOR_MARKERS = ("arize", "langfuse")


def violations(settings: dict, endpoint: str) -> list[str]:
    """Key names that break the baseline; never values."""
    env = settings.get("env", {})
    out = [k for k, v in BASELINE.items() if env.get(k) != v]
    if env.get("OTEL_EXPORTER_OTLP_ENDPOINT") != endpoint:
        out.append("OTEL_EXPORTER_OTLP_ENDPOINT")
    out += [k for k in env if k.startswith("OTEL_EXPORTER_OTLP_") and k not in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL")]
    out += [k for k in CONTENT_KEYS if env.get(k) not in (None, "", "0", "false")]
    out += [k for k in PER_LAUNCH_KEYS if k in env]
    out += [k for k in env if k.startswith(VENDOR_ENV_PREFIXES)]
    out += [k for k in ("OTEL_LOGS_EXPORT_INTERVAL",) if k in env]
    if int(env.get("OTEL_METRIC_EXPORT_INTERVAL") or 60000) < 60000:
        out.append("OTEL_METRIC_EXPORT_INTERVAL")
    for section in ("extraKnownMarketplaces", "pluginConfigs"):
        out += [f"{section}:{k}" for k in settings.get(section, {}) if any(m in k.lower() for m in VENDOR_MARKERS)]
    out += [f"enabledPlugins:{k}" for k, on in settings.get("enabledPlugins", {}).items()
            if on and any(m in k.lower() for m in VENDOR_MARKERS)]
    return sorted(set(out))
```

`tests/settings/conftest.py`:
```python
import json
import os
from pathlib import Path

import pytest


def _load(var: str, default: str | None):
    raw = os.environ.get(var, default)
    if not raw:
        pytest.skip(f"{var} not set")
    path = Path(os.path.expanduser(raw))
    if not path.exists():
        pytest.skip(f"{var}: no file at the configured path")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def settings_a():
    return _load("CLAUDE_SETTINGS_A", "~/.claude/settings.json")


@pytest.fixture
def settings_b():
    return _load("CLAUDE_SETTINGS_B", None)
```

`tests/settings/test_hygiene.py`:
```python
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
    assert violations(settings_a, ENDPOINT_A) == []


def test_settings_b_matches_baseline(settings_b):
    assert violations(settings_b, ENDPOINT_B) == []


def test_environments_agree_except_endpoint(settings_a, settings_b):
    a, b = settings_a.get("env", {}), settings_b.get("env", {})
    keys = {k for k in set(a) | set(b) if k.startswith(("OTEL_", "CLAUDE_CODE_ENABLE", "CLAUDE_CODE_ENHANCED"))}
    keys.discard("OTEL_EXPORTER_OTLP_ENDPOINT")
    assert sorted(k for k in keys if a.get(k) != b.get(k)) == []
```

`tests/claude/conftest.py`:
```python
import http.server
import os
import shutil
import threading
from dataclasses import dataclass, field

import pytest

collect_ignore_glob = [] if os.environ.get("RUN_CLAUDE_CLI") == "1" and shutil.which("claude") else ["test_*.py"]


@dataclass
class Receiver:
    base: str
    bodies: list[bytes] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{self.base}/v1/logs"

    def saw(self, needle: str) -> bool:
        return any(needle.encode() in b for b in self.bodies)


@pytest.fixture
def receiver():
    bodies, paths = [], []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            paths.append(self.path)
            bodies.append(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Receiver(base=f"http://127.0.0.1:{server.server_address[1]}", bodies=bodies, paths=paths)
    server.shutdown()
```

`tests/claude/test_precedence.py`: port `tests/telemetry/test_cli_env_precedence.py` from the earlier validation project (commit `feaf6e7`) **verbatim**, with only these changes:
- replace the `pytestmark` skip markers with nothing (gating is in conftest);
- import `Receiver` from `tests.claude.conftest`;
- load user settings via `json.loads(Path(os.path.expanduser(os.environ.get("CLAUDE_SETTINGS_A", "~/.claude/settings.json"))).read_text())` in a `user_env` fixture.

It keeps its four tests: `test_settings_flag_overrides_user_settings`, `test_process_env_cannot_override_a_key_user_settings_set`, `test_process_env_applies_a_key_user_settings_leave_unset`, `test_native_traces_and_content_on_subscription`. Fetch the source with:
```bash
git -C <validation-project checkout> show feaf6e7:tests/telemetry/test_cli_env_precedence.py
```

`tests/claude/test_end_to_end.py`:
```python
"""Real claude -p through the launcher -> running stack -> Phoenix (and OpenObserve if enabled)."""

import subprocess
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def psql(sql: str) -> str:
    return subprocess.run(["docker", "compose", "exec", "-T", "phoenix-db", "psql", "-U", "phoenix", "-d", "phoenix", "-Atc", sql],
                          cwd=REPO, capture_output=True, text=True).stdout.strip()


def test_launcher_prompt_reaches_phoenix():
    marker = f"e2e-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as cwd:
        subprocess.run(["bash", str(REPO / "launchers" / "claude-traced.sh"), "-p", f"Reply with the single word ok. {marker}",
                        "--tools", "", "--no-session-persistence", "--output-format", "json"],
                       cwd=cwd, check=True, capture_output=True, text=True, timeout=240)
    deadline = time.time() + 60
    found = ""
    while time.time() < deadline and not found:
        found = psql(f"select count(*) from spans where name='claude_code.interaction' and attributes->>'user_prompt' like '%{marker}%'")
        found = "" if found in ("", "0") else found
        time.sleep(3)
    assert found, "prompt text not found on a Phoenix interaction span"
```
The test runs `docker compose exec` from `REPO`, so Compose reads the owner's `.env` for the project name.

- [ ] **Step 3: Run to verify tier 2 fails, then passes**

Before creating `keys.py`: `uv run pytest tests/settings -v` fails with ImportError. After creating all files, on this workstation with `CLAUDE_SETTINGS_B=/mnt/c/Users/<user>/.claude/settings.json`:

Run: `uv run pytest tests/settings -v`
Expected: fixtures tests PASS; `settings_a` / `settings_b` tests PASS. They skip on a machine without those files.

- [ ] **Step 4: Run tier 4**

With the owner's stack up and `.env` configured:

Run: `RUN_CLAUDE_CLI=1 uv run pytest tests/claude -v`
Expected: 5 PASS (4 precedence + 1 end to end), in about a minute. Without `RUN_CLAUDE_CLI=1`: 0 collected.

- [ ] **Step 5: Commit**

```bash
git add tests/settings/ tests/claude/
git commit -m "test: settings hygiene (tier 2) and opt-in Claude CLI tests (tier 4)"
```

---

### Task 7: Documentation

**Files:**
- Create: `README.md`, `docs/concepts.md`, `docs/findings.md`, `docs/dual-environment.md`, `docs/pipelines.md`, `SECURITY.md`, `CHANGELOG.md`, `tests/offline/test_docs.py`

**Interfaces:**
- Consumes: every file and Make target from Tasks 1–6.

- [ ] **Step 1: Write the failing test**

`tests/offline/test_docs.py`:
```python
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]


def test_required_docs_exist():
    for name in ("README.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", "docs/concepts.md",
                 "docs/findings.md", "docs/dual-environment.md", "docs/pipelines.md"):
        assert (REPO / name).is_file(), name


def test_relative_links_resolve():
    broken = []
    for doc in DOCS:
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", doc.read_text()):
            if not (doc.parent / target).exists():
                broken.append(f"{doc.name} -> {target}")
    assert not broken, broken


def test_findings_pin_the_claude_code_version():
    assert "2.1.283" in (REPO / "docs" / "findings.md").read_text()


def test_readme_warns_about_content_capture():
    text = (REPO / "README.md").read_text().lower()
    assert "privacy" in text and "content" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/offline/test_docs.py -v`
Expected: FAIL (missing docs)

- [ ] **Step 3: Write the docs**

Content sources for each file, all in the earlier validation project at merge commit `8293f17`. Rewrite them in generic terms: no personal paths, session IDs or private project names.

| File | Required sections and source |
|---|---|
| `README.md` | 1-paragraph summary; **Quickstart** (`make init`, `make up`, copy `examples/user-settings.json` into `~/.claude/settings.json` `env`, start a **new** Claude Code session, open `http://localhost:${PHOENIX_PORT}`); **Modes** table (single / dual-env / + OpenObserve, with the `.env` keys each needs); **What you get** table (kept vs added by content flags; source: getting-started guide §5); **Privacy** section (content capture copies whatever sessions read, identifiers like `user.email` always ship); **Verify** (`make verify`, `verify-settings`, `verify-claude`); **Disclaimer** (not affiliated with Anthropic, Arize or OpenObserve); links to all docs; License: MIT |
| `docs/concepts.md` | Settings scopes table (user / project / local / shell / `--settings` / managed, and what each can do for telemetry); rules of thumb; signal routing (traces → Phoenix + files; metrics/logs → files, + OpenObserve with the profile); content flags; interactive vs headless detailed tracing. Source: getting-started guide §1, §5 and the interactive-vs-headless section |
| `docs/findings.md` | Spec §4 items 1–8, each with *Observed on*: Claude Code 2.1.283, 2026-09-27; *Evidence*: which run; *Re-checked by*: test name in `tests/claude/` or "manual". Source: research doc claims table, configuration matrix, skill probe, noise section |
| `docs/dual-environment.md` | Two receivers on one Docker Desktop engine; `.env` values (`COLLECTOR_OVERLAY_1=dual-env`, `ENV_A_NAME=wsl`, `ENV_B_NAME=windows`); the second OS's user settings use `:4320`; Windows launcher usage and setting `OTEL_EXPORTER_OTLP_ENDPOINT` in the shell profile for `-Detailed`; Remote Control for cross-session messaging (Windows sessions register under a generated name) |
| `docs/pipelines.md` | For `claude -p` workers: per-call keys only (content flags, `OTEL_RESOURCE_ATTRIBUTES` incl. `openinference.project.name`, `TRACEPARENT`); `--strict-mcp-config --disable-slash-commands` (measured 547,782 → 4,247 cache-creation tokens); never `--bare` (breaks subscription auth); claude.ai connectors and `deniedMcpServers` |
| `SECURITY.md` | Ports bind `127.0.0.1`; `.env` is mode 600 and gitignored; what content capture stores and where (`data/out`, Phoenix, OpenObserve); how to report issues (GitHub private vulnerability reporting) |
| `CHANGELOG.md` | `## 0.1.0 - unreleased`: initial stack, tested with Claude Code 2.1.283, collector 0.140.1, Phoenix 19.13.0 |

- [ ] **Step 4: Run the tests to verify they pass, including the scrub**

Run: `uv run pytest tests/offline -v`
Expected: all PASS, including `test_repository_has_no_personal_data` over the new docs.

- [ ] **Step 5: Commit**

```bash
git add README.md SECURITY.md CHANGELOG.md docs/ tests/offline/test_docs.py
git commit -m "docs: README, concepts, findings, dual-environment, pipelines, security"
```

---

### Task 8: Verify targets and CI

**Files:**
- Modify: `Makefile` (append targets)
- Create: `.github/workflows/verify.yml`

**Interfaces:**
- Consumes: the test directories from Tasks 1–7.

- [ ] **Step 1: Add the verify targets to the `Makefile`**

Replace the `.PHONY` line and append:
```makefile
verify:
	uv run pytest tests/offline tests/smoke -v

verify-settings:
	uv run pytest tests/settings -v

verify-claude:
	RUN_CLAUDE_CLI=1 uv run pytest tests/claude -v
```

- [ ] **Step 2: Write `.github/workflows/verify.yml`**

```yaml
name: verify
on:
  push:
    branches: [main]
  pull_request:

jobs:
  offline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync
      - run: uv run pytest tests/offline -v

  smoke:
    runs-on: ubuntu-latest
    needs: offline
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync
      - run: uv run pytest tests/smoke -v -m docker
```

- [ ] **Step 3: Run the full local gate**

Run: `make verify`
Expected: offline tests PASS, and 10 smoke tests PASS (4 stack combinations, the Phoenix 405 check, 4 `otelcol validate` combinations and its negative case).

Run: `make verify-settings`
Expected: PASS (or skip where settings files are absent).

- [ ] **Step 4: Commit**

```bash
git add Makefile .github/workflows/verify.yml
git commit -m "ci: verify targets and GitHub Actions for offline and smoke tiers"
```

---

### Task 9: Owner review and public release (owner-gated)

**Files:** none new. Fixes land in whichever files the review flags.

- [ ] **Step 1: Hand off for review**

Stop and ask the owner to run `/code-review ultra` in `~/claude-code-otel-local` on the v1 branch. It needs no GitHub remote. Do not start this review yourself; it is user-triggered and billed.

- [ ] **Step 2: Apply the findings**

For each accepted finding: write a test that reproduces it, fix it, then run `make verify`. Commit one fix per finding: `fix: <finding>`.

- [ ] **Step 3: Create the public repo and push** (only after the owner says go)

```bash
gh repo create <owner>/claude-code-otel-local --public --description "Local, native-only observability for Claude Code's OpenTelemetry export" --source . --push
```
Expected: the repo exists, `main` is pushed, and the `verify` workflow runs both jobs green.

---

### Task 10: Migrating from an existing local collector (generic guidance)

For a user who already runs a local OTel collector and Phoenix for Claude Code. Every step that stops, starts or deletes something needs the user's approval.

- [ ] **Step 1: Write `.env` with the same ports**

`make init`, then set the receiver ports to the ones Claude Code settings already use (for example `ENV_A_PORT=4318`, plus `COLLECTOR_OVERLAY_1=dual-env` and `ENV_B_PORT=4320` for a second environment). Move `PHOENIX_PORT` or `OPENOBSERVE_PORT` if another stack still holds 6006 or 5080. Claude Code settings then need no change.

- [ ] **Step 2: Stop the old collector and Phoenix** (keep their volumes)

```bash
docker compose -f <old-collector-compose-file> down
docker compose -f <old-phoenix-compose-file> down   # without -v: keeps the old data
```

- [ ] **Step 3: Start this stack and verify**

Run: `make up && make verify-settings && make verify-claude`
Expected: all PASS.

In a dual-environment setup, start a session in the second environment, send one prompt, then check:
```bash
docker compose exec -T phoenix-db psql -U phoenix -d phoenix -Atc \
  "select count(*) from spans where attributes->'deployment'->'environment'->>'name'='windows' and start_time > now() - interval '10 minutes'"
```
Expected: `> 0`.

- [ ] **Step 4: Refresh copies and references**

Copy the launchers to wherever copies were kept (for example `C:\Users\<user>\.claude\scripts\` on Windows). Point any downstream projects or docs that referenced the old stack at this repo; the endpoints are unchanged.

- [ ] **Step 5: Remove the old volume only after confirming**

List the old Phoenix volume (`docker volume ls`), confirm nothing in it is still needed, then remove it with `docker volume rm <old-phoenix-volume>`.
