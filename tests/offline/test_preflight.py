import base64
import importlib.util
import os
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
    "OPENOBSERVE_ROOT_PASSWORD": "yY1-" * 6,
}
GOOD["OPENOBSERVE_BASIC_AUTH"] = base64.b64encode(
    f'{GOOD["OPENOBSERVE_ROOT_EMAIL"]}:{GOOD["OPENOBSERVE_ROOT_PASSWORD"]}'.encode()).decode()


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
    # compose.yaml always publishes ENV_B_PORT, even in single mode, so it must be free too.
    assert set(preflight.active_ports(dict(GOOD))) == {"ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT"}
    full = dict(GOOD, COLLECTOR_OVERLAY_1="dual-env", COLLECTOR_OVERLAY_2="openobserve", COMPOSE_PROFILES="openobserve")
    assert set(preflight.active_ports(full)) == {"ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT", "OPENOBSERVE_PORT"}


def test_check_ports_reports_busy_port():
    errors = preflight.check_ports(dict(GOOD), is_free=lambda port: port != 6006)
    assert errors == ["port 6006 (PHOENIX_PORT) is already in use on 127.0.0.1; change it in .env or stop the other service"]


def test_check_env_openobserve_retention_minimum():
    # OpenObserve refuses to start (crash loop) with ZO_COMPACT_DATA_RETENTION_DAYS below 3.
    on = dict(GOOD, COLLECTOR_OVERLAY_2="openobserve", COMPOSE_PROFILES="openobserve")
    errors = preflight.check_env(dict(on, OPENOBSERVE_RETENTION_DAYS="1"), REPO / "collector")
    assert any("OPENOBSERVE_RETENTION_DAYS" in e for e in errors)
    assert preflight.check_env(dict(on, OPENOBSERVE_RETENTION_DAYS="3"), REPO / "collector") == []


def test_check_env_openobserve_password_policy():
    on = dict(GOOD, COLLECTOR_OVERLAY_2="openobserve", COMPOSE_PROFILES="openobserve")
    errors = preflight.check_env(dict(on, OPENOBSERVE_ROOT_PASSWORD="alllowercaseletters"), REPO / "collector")
    assert any("OPENOBSERVE_ROOT_PASSWORD" in e for e in errors)
    auth = base64.b64encode(f'{on["OPENOBSERVE_ROOT_EMAIL"]}:abcDEF123-xyz'.encode()).decode()
    ok = dict(on, OPENOBSERVE_ROOT_PASSWORD="abcDEF123-xyz", OPENOBSERVE_BASIC_AUTH=auth)
    assert preflight.check_env(ok, REPO / "collector") == []


def test_check_env_openobserve_basic_auth_matches_credentials():
    import base64
    on = dict(GOOD, COLLECTOR_OVERLAY_2="openobserve", COMPOSE_PROFILES="openobserve")
    good = base64.b64encode(f'{on["OPENOBSERVE_ROOT_EMAIL"]}:{on["OPENOBSERVE_ROOT_PASSWORD"]}'.encode()).decode()
    assert preflight.check_env(dict(on, OPENOBSERVE_BASIC_AUTH=good), REPO / "collector") == []
    # Email edited after init-env: the collector would get 401s while JSONL still fills.
    errors = preflight.check_env(dict(on, OPENOBSERVE_BASIC_AUTH=good, OPENOBSERVE_ROOT_EMAIL="me@example.com"),
                                 REPO / "collector")
    assert any("OPENOBSERVE_BASIC_AUTH" in e for e in errors)


def test_check_data_dir_ok_for_own_writable_dir(tmp_path):
    env = dict(GOOD, HOST_UID=str(os.getuid()))
    assert preflight.check_data_dir(tmp_path, env) == []


def test_check_data_dir_rejects_unwritable_dir(tmp_path):
    # e.g. data/out recreated by Docker as root: the collector can't write and capture stops silently.
    out = tmp_path / "out"
    out.mkdir()
    out.chmod(0o555)
    try:
        errors = preflight.check_data_dir(out, dict(GOOD, HOST_UID=str(os.getuid())))
    finally:
        out.chmod(0o755)
    assert any("not writable" in e for e in errors)


def test_check_data_dir_rejects_owner_other_than_host_uid(tmp_path):
    errors = preflight.check_data_dir(tmp_path, dict(GOOD, HOST_UID=str(os.getuid() + 1)))
    assert any("HOST_UID" in e for e in errors)


def test_parse_env_strips_quotes_like_compose():
    env = preflight.parse_env('A="secretpass123"\nB=\'x # not a comment\'\nC="a b" # trailing\n')
    assert env == {"A": "secretpass123", "B": "x # not a comment", "C": "a b"}


def test_quoted_password_without_special_character_is_rejected():
    env = dict(GOOD, COLLECTOR_OVERLAY_1="openobserve", COMPOSE_PROFILES="openobserve")
    text = "".join(f"{k}={v}\n" for k, v in env.items() if k != "OPENOBSERVE_ROOT_PASSWORD")
    parsed = preflight.parse_env(text + 'OPENOBSERVE_ROOT_PASSWORD="Secretpass123"\n')
    errors = preflight.check_env(parsed, REPO / "collector")
    assert any("OPENOBSERVE_ROOT_PASSWORD must be" in e for e in errors)


def test_ensure_data_dir_creates_owner_only_dir_on_any_path(tmp_path):
    old = os.umask(0o022)
    try:
        out = tmp_path / "elsewhere" / "capture" / "out"
        preflight.ensure_data_dir(out)
    finally:
        os.umask(old)
    assert out.stat().st_mode & 0o777 == 0o700


def test_non_numeric_or_out_of_range_port_is_an_error_not_a_traceback():
    errors = preflight.check_env(dict(GOOD, ENV_A_PORT="43l8", PHOENIX_PORT="70000"), REPO / "collector")
    assert any(e.startswith("ENV_A_PORT must be a port number") for e in errors)
    assert any(e.startswith("PHOENIX_PORT must be a port number") for e in errors)
    assert "ENV_A_PORT" not in preflight.active_ports(dict(GOOD, ENV_A_PORT="43l8"))


def test_empty_port_uses_compose_default():
    env = dict(GOOD, ENV_A_PORT="")
    assert preflight.check_env(env, REPO / "collector") == []
    assert preflight.active_ports(env)["ENV_A_PORT"] == 4318


def test_duplicate_ports_are_reported():
    errors = preflight.check_env(dict(GOOD, PHOENIX_PORT="4318"), REPO / "collector")
    assert any("PHOENIX_PORT and ENV_A_PORT are both 4318" in e for e in errors)
