import json
import os
from pathlib import Path

import pytest

from tests.redact import KeysOnly


def _load(var: str, default: str | None):
    raw = os.environ.get(var, default)
    if not raw:
        pytest.skip(f"{var} not set")
    path = Path(os.path.expanduser(raw))
    if not path.exists():
        pytest.skip(f"{var}: no file at the configured path")
    return KeysOnly(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
def settings_a():
    return _load("CLAUDE_SETTINGS_A", "~/.claude/settings.json")


@pytest.fixture
def settings_b():
    return _load("CLAUDE_SETTINGS_B", None)
