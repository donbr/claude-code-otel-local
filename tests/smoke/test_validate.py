"""spec §5 tier 3: the real collector accepts every overlay combination (`otelcol validate`)."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.offline.collector_graph import COMBOS

pytestmark = pytest.mark.docker

REPO = Path(__file__).resolve().parents[2]
IMAGE = yaml.safe_load((REPO / "compose.yaml").read_text())["services"]["otel-collector"]["image"]


def validate(collector_dir: Path, o1: str, o2: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        # Run as this user, as compose.yaml does, so a private (0700) directory is readable.
        ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{collector_dir}:/etc/otelcol:ro",
         "-e", "ENV_A_NAME=a", "-e", "ENV_B_NAME=b", "-e", "OPENOBSERVE_BASIC_AUTH=eA==",
         IMAGE, "validate", "--config=/etc/otelcol/base.yaml",
         f"--config=/etc/otelcol/{o1}.yaml", f"--config=/etc/otelcol/{o2}.yaml"],
        capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("o1,o2", COMBOS, ids=lambda x: x)
def test_collector_validates_overlay_combination(o1, o2):
    result = validate(REPO / "collector", o1, o2)
    assert result.returncode == 0, result.stderr[-1500:]


def test_validate_rejects_a_broken_overlay(tmp_path):
    for f in (REPO / "collector").glob("*.yaml"):
        (tmp_path / f.name).write_text(f.read_text())
    (tmp_path / "broken.yaml").write_text("service:\n  pipelines:\n    logs/out:\n      exporters: [file/nope]\n")
    result = validate(tmp_path, "broken", "none")
    assert result.returncode != 0
    assert "file/nope" in result.stderr, result.stderr[-1500:]  # rejected for the config, not a mount error
