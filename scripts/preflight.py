#!/usr/bin/env python3
"""Check .env before `docker compose up`: secrets, overlay/profile consistency, free ports, data dir."""

import base64
import os
import socket
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
REQUIRED = ("PHOENIX_DB_PASSWORD", "HOST_UID", "HOST_GID")


def parse_env(text: str) -> dict[str, str]:
    """Read .env the way Compose does for plain values: quotes are stripped, and ` #` starts a
    comment only outside quotes. (Escape sequences inside double quotes aren't expanded.)"""
    env = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ("'", '"') and value.find(value[0], 1) > 0:
            value = value[1:value.find(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].strip()
        env[key.strip()] = value
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
        pw = env.get("OPENOBSERVE_ROOT_PASSWORD", "")
        expected = base64.b64encode(f'{env.get("OPENOBSERVE_ROOT_EMAIL", "")}:{pw}'.encode()).decode()
        if pw and env.get("OPENOBSERVE_BASIC_AUTH") and env["OPENOBSERVE_BASIC_AUTH"] != expected:
            errors.append("OPENOBSERVE_BASIC_AUTH does not match OPENOBSERVE_ROOT_EMAIL:OPENOBSERVE_ROOT_PASSWORD; "
                          "set it to base64 of email:password (OpenObserve keeps the root credentials from its "
                          "first start, so changing them later also needs `docker compose down -v`)")
        if pw and not (8 <= len(pw) <= 128 and any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                       and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)):
            errors.append("OPENOBSERVE_ROOT_PASSWORD must be 8-128 characters with lower, upper, digit and "
                          "special characters (OpenObserve refuses to start otherwise)")
        retention = env.get("OPENOBSERVE_RETENTION_DAYS", "30") or "30"
        if not retention.isdigit() or int(retention) < 3:
            errors.append("OPENOBSERVE_RETENTION_DAYS must be a whole number of at least 3 (OpenObserve refuses less)")
    return errors + check_port_values(env)


PORT_DEFAULTS = {"ENV_A_PORT": "4318", "ENV_B_PORT": "4320", "PHOENIX_PORT": "6006", "OPENOBSERVE_PORT": "5080"}


def _port_values(env: dict[str, str]) -> dict[str, str]:
    # ENV_B_PORT is published in every mode (nothing listens on it without the dual-env overlay).
    # An empty value falls back to the default, as `${VAR:-default}` does in compose.yaml.
    keys = ["ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT"]
    if "openobserve" in _profiles(env):
        keys.append("OPENOBSERVE_PORT")
    return {k: env.get(k) or PORT_DEFAULTS[k] for k in keys}


def check_port_values(env: dict[str, str]) -> list[str]:
    values = _port_values(env)
    errors = [f"{k} must be a port number between 1 and 65535" for k, v in values.items()
              if not (v.isdigit() and 1 <= int(v) <= 65535)]
    seen: dict[str, str] = {}
    for k, v in values.items():
        if v in seen:
            errors.append(f"{k} and {seen[v]} are both {v}; each published port must be different")
        seen.setdefault(v, k)
    return errors


def active_ports(env: dict[str, str]) -> dict[str, int]:
    """Valid ports only; check_port_values reports the rest."""
    return {k: int(v) for k, v in _port_values(env).items() if v.isdigit() and 1 <= int(v) <= 65535}


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def check_ports(env: dict[str, str], is_free: Callable[[int], bool] = _is_free) -> list[str]:
    return [
        f"port {port} ({name}) is already in use on 127.0.0.1; change it in .env or stop the other service"
        for name, port in active_ports(env).items()
        if not is_free(port)
    ]


def ensure_data_dir(out: Path) -> None:
    """Create the capture directory owner-only: it holds captured content in plain text."""
    out.mkdir(mode=0o700, parents=True, exist_ok=True)


def check_data_dir(out: Path, env: dict[str, str]) -> list[str]:
    """The collector runs as HOST_UID and must be able to write here, or capture stops silently."""
    errors = []
    if not os.access(out, os.W_OK):
        errors.append(f"{out} is not writable; fix it with: sudo chown -R $(id -u):$(id -g) {out}")
    uid = env.get("HOST_UID", "")
    if hasattr(os, "getuid") and uid.isdigit() and out.stat().st_uid != int(uid):
        errors.append(f"{out} is owned by uid {out.stat().st_uid}, not HOST_UID={uid}; "
                      f"run: sudo chown -R {uid}:{env.get('HOST_GID', uid)} {out}")
    return errors


def main(argv: list[str]) -> int:
    env_path = REPO / ".env"
    if not env_path.is_file():
        print("no .env; run scripts/init-env.sh", file=sys.stderr)
        return 1
    env = parse_env(env_path.read_text())
    errors = check_env(env, REPO / "collector")
    if "--skip-ports" not in argv:
        errors += check_ports(env)
    out = REPO / env.get("DATA_DIR", "./data") / "out"
    ensure_data_dir(out)
    errors += check_data_dir(out, env)
    for e in errors:
        print(f"preflight: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
