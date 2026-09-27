import http.server
import os
import shutil
import threading
from dataclasses import dataclass, field

import pytest

from tests.redact import Bodies

collect_ignore_glob = [] if os.environ.get("RUN_CLAUDE_CLI") == "1" and shutil.which("claude") else ["test_*.py"]


@dataclass
class Receiver:
    base: str
    bodies: list[bytes] = field(default_factory=Bodies, repr=False)  # raw telemetry: identifiers, content
    paths: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{self.base}/v1/logs"

    def __post_init__(self):
        if not isinstance(self.bodies, Bodies):
            self.bodies = Bodies(self.bodies)

    def saw(self, needle: str) -> bool:
        return any(needle.encode() in b for b in self.bodies)


@pytest.fixture
def receiver():
    bodies, paths = Bodies(), []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            paths.append(self.path)
            bodies.append(self._body())
            self.send_response(200)
            self.end_headers()

        def _body(self) -> bytes:
            # Detailed beta tracing exports OTLP/JSON with chunked transfer encoding (no Content-Length).
            if self.headers.get("Transfer-Encoding", "").lower() != "chunked":
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = b""
            while size := int(self.rfile.readline().split(b";")[0].strip() or b"0", 16):
                data += self.rfile.read(size)
                self.rfile.readline()
            self.rfile.readline()
            return data

        def log_message(self, format, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Receiver(base=f"http://127.0.0.1:{server.server_address[1]}", bodies=bodies, paths=paths)
    server.shutdown()
