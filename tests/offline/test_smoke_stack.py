"""Offline checks of the smoke harness itself (no Docker needed)."""

import subprocess

import pytest

from tests.smoke import stack as stack_mod


def test_free_port_avoids_ephemeral_and_windows_dynamic_ranges():
    # Docker Desktop cannot forward ports Windows/Hyper-V reserves; those sit in the dynamic ranges.
    for _ in range(50):
        assert stack_mod.PORT_RANGE[0] <= stack_mod._free_port() <= stack_mod.PORT_RANGE[1]
    assert stack_mod.PORT_RANGE[1] < 32768


def _failing_up(calls, fail_times):
    def fake(self, *args, check=True):
        calls.append(args[0])
        if args[0] == "up" and calls.count("up") <= fail_times:
            raise subprocess.CalledProcessError(1, ["docker", "compose", "up"], "",
                                                "Error response from daemon: ports are not available")
        return subprocess.CompletedProcess(args, 0, "", "")
    return fake


def test_enter_tears_down_and_retries_on_port_error(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(stack_mod.Stack, "_compose", _failing_up(calls, fail_times=1))
    monkeypatch.setattr(stack_mod.Stack, "_wait_port", staticmethod(lambda port, timeout=60: None))
    s = stack_mod.Stack("none", "none", tmp_path)
    first_ports = dict(s.ports)
    s.__enter__()
    assert calls == ["up", "down", "up"]
    assert s.ports != first_ports
    assert s.env_file.read_text().count(f"ENV_A_PORT={s.ports['ENV_A_PORT']}\n") == 1


def test_enter_tears_down_and_reports_stderr_on_other_errors(tmp_path, monkeypatch):
    calls = []

    def fake(self, *args, check=True):
        calls.append(args[0])
        if args[0] == "up":
            raise subprocess.CalledProcessError(1, ["docker"], "", "dependency failed to start")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(stack_mod.Stack, "_compose", fake)
    s = stack_mod.Stack("none", "none", tmp_path)
    with pytest.raises(RuntimeError, match="dependency failed to start"):
        s.__enter__()
    assert calls == ["up", "down"]


def test_stack_openobserve_password_meets_policy(tmp_path):
    from tests.offline.test_init_env import meets_openobserve_policy
    for i in range(10):
        s = stack_mod.Stack("openobserve", "none", tmp_path / str(i))
        assert meets_openobserve_policy(s.env["OPENOBSERVE_ROOT_PASSWORD"])


def test_enter_tears_down_when_collector_port_never_opens(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(stack_mod.Stack, "_compose", _failing_up(calls, fail_times=0))

    def never(port, timeout=60):
        raise TimeoutError("port never opened")

    monkeypatch.setattr(stack_mod.Stack, "_wait_port", staticmethod(never))
    s = stack_mod.Stack("none", "none", tmp_path)
    with pytest.raises(TimeoutError):
        s.__enter__()
    assert calls == ["up", "down"]
