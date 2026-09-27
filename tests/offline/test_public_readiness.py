from pathlib import Path

import pytest

from tests.offline.scrub import find_personal_data, tracked_files

REPO = Path(__file__).resolve().parents[2]


# Samples are assembled from pieces so this file (and the plan) never contains a literal match.
@pytest.mark.parametrize(
    "text,kind",
    [
        ("contact me at someone" + "@" + "mail.test.org", "email"),
        ("path /home" + "/alice/project", "home_path"),
        ("C:" + "\\Users\\" + "alice" + "\\.claude", "windows_user_path"),
        ("/mnt/c" + "/Users/" + "alice/.claude", "windows_user_path"),
        ("C:" + "/Users/" + "alice/.claude", "windows_user_path"),
        ("open /Users" + "/alice/project", "mac_user_path"),
        ("see the temporal" + "-zero-disk plan", "private_name"),
        ("when temporal" + "-claude-worker launches", "private_name"),
        ("ported from graphiti" + "-test", "private_name"),
        ("cd ~/aie" + "-onramp/x", "private_name"),
        ("repo at ~/car" + "eer/claude-code-otel-local", "private_name"),
        ("the hci" + "-canon MCP servers", "private_name"),
        ("stop claude-otel" + "-stack first", "private_name"),
        ("session " + "0a1b2c3d" + "-0000-4000-8000-" + "0123456789ab", "uuid"),
        ("key " + "sk-ant-" + "api03-abcdefghijklmnop", "token"),
        ("Authorization=" + "Basic " + "YWRtaW46c2VjcmV0cGFzc3dvcmQ=", "token"),
    ],
)
def test_detects_personal_data(text, kind):
    assert kind in find_personal_data(text)


@pytest.mark.parametrize(
    "text",
    [
        "admin@example.com",
        r"C:\Users\<user>\.claude\settings.json",
        "/home/<user>/project and ~/.claude/settings.json",
        "/mnt/c/Users/<user>/.claude/settings.json",
        "C:/Users/Public/Documents",
        "https://example.com/api/Users/list",
        "a downstream Temporal worker project",
        "career advice and graphiti in general",
        "sha256:e61b2ec06fa1f2f96fb9ffbdf55a7484290931188f82b05393def69b85eeaba2",
        "Authorization=Basic <redacted>",
    ],
)
def test_allows_placeholders(text):
    assert find_personal_data(text) == []


def test_repository_has_no_personal_data():
    hits = {}
    for path in tracked_files(REPO):
        kinds = find_personal_data(path.read_text(encoding="utf-8", errors="replace"))
        if kinds:
            hits[str(path.relative_to(REPO))] = kinds
    assert not hits, f"personal data patterns found (kinds only): {hits}"


def test_gitattributes_line_endings():
    text = (REPO / ".gitattributes").read_text()
    assert "*.sh text eol=lf" in text
    assert "*.ps1 text eol=crlf" in text
