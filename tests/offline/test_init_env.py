import base64
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run_init(tmp_path: Path) -> subprocess.CompletedProcess:
    shutil.copy(REPO / ".env.example", tmp_path / ".env.example")
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "init-env.sh", tmp_path / "scripts" / "init-env.sh")
    return subprocess.run(["bash", "scripts/init-env.sh"], cwd=tmp_path, capture_output=True, text=True)


def read_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_init_env_generates_secrets_and_basic_auth(tmp_path):
    assert run_init(tmp_path).returncode == 0
    env = read_env(tmp_path / ".env")
    assert len(env["PHOENIX_DB_PASSWORD"]) >= 24
    assert len(env["OPENOBSERVE_ROOT_PASSWORD"]) >= 24
    expected = base64.b64encode(f'{env["OPENOBSERVE_ROOT_EMAIL"]}:{env["OPENOBSERVE_ROOT_PASSWORD"]}'.encode()).decode()
    assert env["OPENOBSERVE_BASIC_AUTH"] == expected


def test_init_env_writes_uid_gid_and_data_dir(tmp_path):
    run_init(tmp_path)
    env = read_env(tmp_path / ".env")
    assert env["HOST_UID"].isdigit() and env["HOST_GID"].isdigit()
    assert (tmp_path / "data" / "out").is_dir()


def test_init_env_refuses_to_overwrite(tmp_path):
    run_init(tmp_path)
    second = subprocess.run(["bash", "scripts/init-env.sh"], cwd=tmp_path, capture_output=True, text=True)
    assert second.returncode != 0
    assert "already exists" in second.stderr


def meets_openobserve_policy(pw: str) -> bool:
    # OpenObserve panics at startup unless the root password has all four character classes.
    return (8 <= len(pw) <= 128 and any(c.islower() for c in pw) and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw))


def test_init_env_openobserve_password_meets_policy(tmp_path):
    # token_urlsafe alone misses a class about a third of the time; ten runs make that visible.
    for i in range(10):
        d = tmp_path / str(i)
        d.mkdir()
        assert run_init(d).returncode == 0
        assert meets_openobserve_policy(read_env(d / ".env")["OPENOBSERVE_ROOT_PASSWORD"])


def test_init_env_creates_env_private_even_with_permissive_umask(tmp_path):
    shutil.copy(REPO / ".env.example", tmp_path / ".env.example")
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "init-env.sh", tmp_path / "scripts" / "init-env.sh")
    # umask 077 must be set before the redirect, not only chmod afterwards; check the script shape.
    text = (tmp_path / "scripts" / "init-env.sh").read_text()
    assert text.index("umask 077") < text.index("> .env")
    subprocess.run(["bash", "-c", "umask 000; bash scripts/init-env.sh"], cwd=tmp_path, check=True,
                   capture_output=True)
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
