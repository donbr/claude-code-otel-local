"""Bring up an isolated copy of the stack (own project name, random ports, temp data dir)."""

import base64
import json
import random
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Below the Linux ephemeral range (32768+) and the Windows dynamic range (49152+), where Hyper-V
# reserves blocks that Docker Desktop cannot forward ("ports are not available").
PORT_RANGE = (20000, 32000)
PORT_KEYS = ("ENV_A_PORT", "ENV_B_PORT", "PHOENIX_PORT", "OPENOBSERVE_PORT")


def _free_port() -> int:
    while True:
        port = random.randint(*PORT_RANGE)
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port


class Stack:
    def __init__(self, overlay_1: str, overlay_2: str, tmp_path: Path):
        self.data_dir = tmp_path / "data"
        (self.data_dir / "out").mkdir(parents=True)
        email, pw = "admin@example.com", secrets.token_urlsafe(24) + "-Aa1"  # OpenObserve password policy
        self.ports = {k: _free_port() for k in PORT_KEYS}
        uses_oo = "openobserve" in (overlay_1, overlay_2)
        self.env = {
            "COMPOSE_PROJECT_NAME": f"ccol-smoke-{secrets.token_hex(4)}",
            "COMPOSE_PROFILES": "openobserve" if uses_oo else "",
            "ENV_A_NAME": "envA", "ENV_B_NAME": "envB",
            "COLLECTOR_OVERLAY_1": overlay_1, "COLLECTOR_OVERLAY_2": overlay_2,
            "PHOENIX_DB_PASSWORD": secrets.token_urlsafe(24), "PHOENIX_RETENTION_DAYS": "1",
            "OPENOBSERVE_ROOT_EMAIL": email, "OPENOBSERVE_ROOT_PASSWORD": pw,
            "OPENOBSERVE_BASIC_AUTH": base64.b64encode(f"{email}:{pw}".encode()).decode(),
            "OPENOBSERVE_RETENTION_DAYS": "3",  # OpenObserve refuses less than 3
            "HOST_UID": str(subprocess.check_output(["id", "-u"], text=True).strip()),
            "HOST_GID": str(subprocess.check_output(["id", "-g"], text=True).strip()),
            "DATA_DIR": str(self.data_dir),
        }
        self.env_file = tmp_path / ".env"
        self._write_env()

    def _write_env(self) -> None:
        self.env.update({k: str(v) for k, v in self.ports.items()})
        self.env_file.write_text("".join(f"{k}={v}\n" for k, v in self.env.items()))

    def _compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", "--env-file", str(self.env_file), *args],
                              cwd=REPO, capture_output=True, text=True, check=check)

    def __enter__(self):
        for attempt in range(3):
            try:
                self._compose("up", "-d", "--wait", "--wait-timeout", "180")
                break
            except subprocess.CalledProcessError as e:
                self._compose("down", "-v", check=False)
                if "ports are not available" in (e.stderr or "") and attempt < 2:
                    self.ports = {k: _free_port() for k in PORT_KEYS}
                    self._write_env()
                    continue
                raise RuntimeError(f"docker compose up failed: {(e.stderr or '')[-1500:]}") from e
        try:
            self._wait_port(self.ports["ENV_A_PORT"])
        except BaseException:
            # __exit__ never runs when __enter__ raises.
            self._compose("down", "-v", check=False)
            raise
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

    def openobserve_search(self, marker: str, field: str = "body") -> int:
        now = int(time.time() * 1_000_000)
        body = json.dumps({"query": {"sql": f"SELECT * FROM \"default\" WHERE str_match({field}, '{marker}')",
                                     "start_time": now - 900_000_000, "end_time": now, "from": 0, "size": 10}}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.ports['OPENOBSERVE_PORT']}/api/default/_search", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Basic {self.env['OPENOBSERVE_BASIC_AUTH']}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return len(json.load(resp).get("hits", []))
        except OSError:
            return 0
