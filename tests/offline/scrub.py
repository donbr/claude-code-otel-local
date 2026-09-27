"""Detect personal data that must never ship in a public repo. Reports pattern kinds only."""

import re
import subprocess
from pathlib import Path

PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "home_path": re.compile(r"/home/(?!<user>|user\b|runner\b)[A-Za-z0-9_.-]+"),
    "windows_user_path": re.compile(
        r"(?:[A-Z]:\\Users\\|[A-Z]:/Users/|/mnt/[a-z]/Users/)(?!<user>|Public\b)[A-Za-z0-9_.-]+", re.IGNORECASE),
    "mac_user_path": re.compile(r"(?<![\w/.:])/Users/(?!<user>|Shared\b)[A-Za-z0-9_.-]+"),
    # The owner's private repos and paths. Written with [-] so this file doesn't match itself.
    "private_name": re.compile(
        r"temporal[-]zero[-]disk|temporal[-]claude[-]worker|graphiti[-]test|aie[-]onramp|~/care[e]r\b|/care[e]r/"
        r"|hci[-]canon|claude[-]otel[-]stack|lila[-]graph", re.IGNORECASE),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
    "token": re.compile(
        r"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|pk-lf-[A-Za-z0-9-]{10,}"
        r"|Basic [A-Za-z0-9+/]{16,}={0,2})"
    ),
}


def find_personal_data(text: str) -> list[str]:
    return sorted(kind for kind, pattern in PATTERNS.items() if pattern.search(text))


def tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    skip_suffixes = {".png", ".jpg", ".ico", ".lock"}
    return [repo / p for p in out if (repo / p).is_file() and Path(p).suffix not in skip_suffixes]
