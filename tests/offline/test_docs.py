import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]


def test_required_docs_exist():
    for name in ("README.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", "docs/concepts.md",
                 "docs/findings.md", "docs/dual-environment.md", "docs/pipelines.md"):
        assert (REPO / name).is_file(), name


def test_relative_links_resolve():
    broken = []
    for doc in DOCS:
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", doc.read_text()):
            if not (doc.parent / target).exists():
                broken.append(f"{doc.name} -> {target}")
    assert not broken, broken


def test_findings_pin_the_claude_code_version():
    assert "2.1.283" in (REPO / "docs" / "findings.md").read_text()


def test_readme_warns_about_content_capture():
    text = (REPO / "README.md").read_text().lower()
    assert "privacy" in text and "content" in text


def test_readme_says_native_windows_needs_a_posix_shell():
    text = (REPO / "README.md").read_text()
    assert "Git Bash" in text and "WSL" in text


def test_design_docs_are_linked_and_covered():
    design = sorted((REPO / "docs" / "design").glob("*.md"))
    assert len(design) == 2 and all(d in DOCS for d in design)
    readme = (REPO / "README.md").read_text()
    for d in design:
        assert f"docs/design/{d.name}" in readme, d.name
