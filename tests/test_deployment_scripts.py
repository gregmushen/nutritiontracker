import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -e\n" + body)
    path.chmod(0o755)


def _deployment_env(tmp_path: Path, deploy_dir: Path) -> Path:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            (
                "NT_DEPLOY_HOST=test-host",
                "NT_DEPLOY_USER=test-user",
                f"NT_DEPLOY_DIR={deploy_dir}",
                "NT_DEPLOY_SERVICE=nutritiontracker",
                f"NT_DEPLOY_DB={deploy_dir / 'data' / 'nutrition.db'}",
                f"NT_DEPLOY_BACKUP_DIR={deploy_dir / 'backups'}",
                "NT_PUBLIC_HOST=nutrition.example.test",
                "",
            )
        )
    )
    return env_file


@pytest.mark.parametrize(
    "script",
    (
        "bin/_deploy-env",
        "bin/db-backup",
        "bin/db-push",
        "bin/deploy",
        "bin/import-off",
        "bin/import-usda",
        "bin/install-systemd",
        "bin/kamal",
    ),
)
def test_shell_scripts_parse(script):
    subprocess.run(["bash", "-n", str(ROOT / script)], check=True)


def test_kamal_wrapper_loads_deployment_environment(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    output = tmp_path / "kamal-output"
    _write_executable(
        fake_bin / "kamal",
        'printf "%s\\n%s\\n" "$NT_DEPLOY_HOST" "$*" > "$KAMAL_TEST_OUTPUT"\n',
    )
    env_file = _deployment_env(tmp_path, tmp_path / "deploy")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NT_DEPLOY_ENV": str(env_file),
        "KAMAL_TEST_OUTPUT": str(output),
    }

    subprocess.run([str(ROOT / "bin/kamal"), "config"], env=env, check=True)

    assert output.read_text().splitlines() == ["test-host", "config"]


def test_kamal_config_omits_empty_ssh_key(tmp_path):
    env = {
        **os.environ,
        "NT_DEPLOY_HOST": "test-host",
        "NT_DEPLOY_USER": "test-user",
        "NT_PUBLIC_HOST": "nutrition.example.test",
        "NT_DEPLOY_SSH_KEY": "",
    }
    rendered = subprocess.run(
        [
            "ruby",
            "-rerb",
            "-e",
            "puts ERB.new(File.read(ARGV[0])).result",
            str(ROOT / "config/deploy.yml"),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "- test-host" in rendered
    assert "keys:" not in rendered


def test_deploy_stops_when_dependency_installation_fails(tmp_path):
    deploy_dir = tmp_path / "deploy"
    fake_bin = tmp_path / "bin"
    (deploy_dir / ".venv/bin").mkdir(parents=True)
    fake_bin.mkdir()
    marker = tmp_path / "alembic-ran"
    _write_executable(fake_bin / "ssh", 'shift\n/bin/bash -c "$1"\n')
    _write_executable(fake_bin / "git", "exit 0\n")
    _write_executable(deploy_dir / ".venv/bin/pip", "exit 42\n")
    _write_executable(
        deploy_dir / ".venv/bin/alembic", f"touch '{marker}'\n"
    )
    env_file = _deployment_env(tmp_path, deploy_dir)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NT_DEPLOY_ENV": str(env_file),
    }

    result = subprocess.run(
        [str(ROOT / "bin/deploy")], env=env, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_db_push_restarts_original_service_when_migration_fails(tmp_path):
    deploy_dir = tmp_path / "deploy"
    data_dir = deploy_dir / "data"
    fake_bin = tmp_path / "bin"
    venv_bin = deploy_dir / ".venv/bin"
    data_dir.mkdir(parents=True)
    fake_bin.mkdir()
    venv_bin.mkdir(parents=True)
    live_db = data_dir / "nutrition.db"
    conn = sqlite3.connect(live_db)
    conn.execute("CREATE TABLE marker (value TEXT)")
    conn.execute("INSERT INTO marker VALUES ('original')")
    conn.commit()
    conn.close()
    incoming = tmp_path / "incoming.db"
    incoming.write_bytes(b"replacement")
    service_log = tmp_path / "systemctl.log"

    _write_executable(fake_bin / "ssh", 'shift\n/bin/bash -c "$1"\n')
    _write_executable(fake_bin / "flock", "exit 0\n")
    _write_executable(
        fake_bin / "rsync",
        'for last; do :; done\n'
        'target="${last#*:}"\n'
        'for arg in "$@"; do\n'
        '  if [[ -f "$arg" ]]; then cp "$arg" "$target"; break; fi\n'
        "done\n",
    )
    _write_executable(fake_bin / "sudo", 'exec "$@"\n')
    _write_executable(
        fake_bin / "systemctl",
        f'printf "%s\\n" "$*" >> "{service_log}"\n',
    )
    _write_executable(
        venv_bin / "python",
        'if [[ "${1:-}" == "-m" ]]; then exit 42; fi\nexec python3 "$@"\n',
    )
    env_file = _deployment_env(tmp_path, deploy_dir)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NT_DEPLOY_ENV": str(env_file),
    }

    result = subprocess.run(
        [str(ROOT / "bin/db-push"), str(incoming)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    conn = sqlite3.connect(live_db)
    value = conn.execute("SELECT value FROM marker").fetchone()[0]
    conn.close()
    assert value == "original"
    assert service_log.exists(), result.stdout + result.stderr
    assert service_log.read_text().splitlines() == [
        "stop nutritiontracker",
        "start nutritiontracker",
    ]


def test_systemd_files_are_created_with_private_defaults():
    install = (ROOT / "bin/install-systemd").read_text()
    db_backup = (ROOT / "bin/db-backup").read_text()
    db_push = (ROOT / "bin/db-push").read_text()
    unit = (ROOT / "deploy/systemd/nutritiontracker.service.template").read_text()

    assert "sudo mktemp '/etc/systemd/system/" in install
    assert "/tmp/$NT_DEPLOY_SERVICE.service" not in install
    assert "umask 077" in install
    assert "umask 077" in db_backup
    assert "umask 077" in db_push
    assert "UMask=0077" in unit
