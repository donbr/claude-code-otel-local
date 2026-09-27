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


PWSH = os.environ.get("PWSH") or shutil.which("pwsh")


def ps_path(path: Path) -> str:
    # A Windows pwsh.exe reached from WSL needs a Windows path.
    if PWSH and PWSH.endswith(".exe"):
        return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    return str(path)


def ps1_parses(path: Path) -> bool:
    # [ref] needs existing variables, so declare the token and error outputs first.
    cmd = (f"$t = $null; $e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
           f"'{ps_path(path)}', [ref]$t, [ref]$e); if ($e.Count) {{ exit 1 }}")
    return subprocess.run([PWSH, "-NoProfile", "-Command", cmd], capture_output=True).returncode == 0


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed (set PWSH to a pwsh binary to run)")
def test_ps1_parses():
    assert ps1_parses(REPO / "launchers" / "claude-traced.ps1")


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed (set PWSH to a pwsh binary to run)")
def test_ps1_parse_check_rejects_broken_script(tmp_path):
    broken = tmp_path / "broken.ps1"
    broken.write_text("if ($true) {\n  Write-Output 'unterminated'\n")
    assert not ps1_parses(broken)


@pytest.mark.skipif(PWSH is None, reason="pwsh not installed (set PWSH to a pwsh binary to run)")
def test_ps1_exits_nonzero_when_claude_is_missing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    script = ps_path(REPO / "launchers" / "claude-traced.ps1")
    cmd = f"$env:PATH = '{ps_path(empty)}'; & '{script}' -p x; exit $LASTEXITCODE"
    result = subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                            capture_output=True, text=True)
    assert "cannot be loaded" not in result.stdout + result.stderr, "execution policy blocked the launcher"
    assert result.returncode != 0


def test_ps1_strips_detailed_from_any_position():
    text = (REPO / "launchers" / "claude-traced.ps1").read_text()
    assert "$ClaudeArgs[0]" not in text
    assert "Where-Object { $_ -ne '-Detailed' }" in text
