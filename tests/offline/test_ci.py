import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "verify.yml"


def test_workflow_token_is_read_only():
    assert yaml.safe_load(WORKFLOW.read_text())["permissions"] == {"contents": "read"}


def test_actions_are_pinned_to_full_commit_shas():
    uses = re.findall(r"uses:\s*(\S+)(.*)", WORKFLOW.read_text())
    assert uses
    for ref, comment in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref
        assert re.search(r"#\s*v\d", comment), f"{ref}: add the version as a comment"


def test_runner_image_is_pinned():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    for name, job in jobs.items():
        assert not job["runs-on"].endswith("-latest"), f"{name}: pin the runner image (e.g. ubuntu-24.04)"
