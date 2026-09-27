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
        # A digest, or a full x.y.z version tag; floating tags such as 16-alpine are not pinned.
        assert re.search(r"@sha256:[0-9a-f]{64}$", image) or re.search(r":\d+\.\d+\.\d+$", image), image
        assert not image.endswith(":latest"), image
