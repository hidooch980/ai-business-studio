from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


def test_encrypted_backup_creates_checksum_and_restricts_permissions(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "pg_dump",
        """#!/usr/bin/env bash
set -eu
for arg in "$@"; do
  case "$arg" in --file=*) output="${arg#--file=}";; esac
done
printf 'plain database dump' > "$output"
""",
    )
    _write_executable(
        bin_dir / "age",
        """#!/usr/bin/env bash
set -eu
[[ "$1" == "--recipient" ]]
shift 2
[[ "$1" == "--output" ]]
output="$2"
input="$3"
cp "$input" "$output"
""",
    )
    pgpass = tmp_path / "backup.pgpass"
    pgpass.write_text("localhost:5432:db:backup:secret\n", encoding="utf-8")
    pgpass.chmod(0o600)
    backup_dir = tmp_path / "encrypted backups"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PGSERVICE": "backup-service",
        "PGPASSFILE": str(pgpass),
        "PGDATABASE": "studio_test",
        "BACKUP_DIR": str(backup_dir),
        "BACKUP_AGE_RECIPIENT": "age1testrecipient",
        "BACKUP_RETENTION_DAYS": "0",
    }

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/backup-postgres.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    backups = list(backup_dir.glob("studio_test-*.dump.age"))
    assert len(backups) == 1
    backup = backups[0]
    checksum = Path(f"{backup}.sha256")
    assert backup.read_text(encoding="utf-8") == "plain database dump"
    assert checksum.exists()
    expected = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="utf-8").startswith(expected)
    assert backup.stat().st_mode & 0o777 == 0o600
    assert checksum.stat().st_mode & 0o777 == 0o600


def test_restore_requires_confirmation_and_runs_atomically_after_checksum(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    restore_args = tmp_path / "restore-args.txt"
    restore_input = tmp_path / "restore-input.txt"
    _write_executable(
        bin_dir / "age",
        """#!/usr/bin/env bash
set -eu
[[ "$1" == "--decrypt" ]]
printf 'decrypted database dump'
""",
    )
    _write_executable(
        bin_dir / "pg_restore",
        """#!/usr/bin/env bash
set -eu
printf '%s\n' "$@" > "$RESTORE_ARGS"
cat > "$RESTORE_INPUT"
""",
    )
    pgpass = tmp_path / "restore.pgpass"
    identity = tmp_path / "age-identity.txt"
    backup = tmp_path / "studio_test.dump.age"
    pgpass.write_text("localhost:5432:db:restore:secret\n", encoding="utf-8")
    identity.write_text("AGE-SECRET-KEY-TEST", encoding="utf-8")
    backup.write_text("encrypted database dump", encoding="utf-8")
    for path in (pgpass, identity):
        path.chmod(0o600)
    checksum = Path(f"{backup}.sha256")
    checksum.write_text(
        f"{hashlib.sha256(backup.read_bytes()).hexdigest()}  {backup.name}\n",
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PGSERVICE": "recovery-service",
        "PGPASSFILE": str(pgpass),
        "PGDATABASE": "studio_recovery",
        "BACKUP_FILE": str(backup),
        "AGE_IDENTITY_FILE": str(identity),
        "RESTORE_ARGS": str(restore_args),
        "RESTORE_INPUT": str(restore_input),
    }
    script = str(ROOT / "scripts/restore-postgres.sh")

    refused = subprocess.run(
        ["bash", script],
        check=False,
        capture_output=True,
        text=True,
        env={**environment, "RESTORE_CONFIRMATION": "wrong"},
    )
    assert refused.returncode != 0
    assert "explicit target-database confirmation" in refused.stderr
    assert not restore_args.exists()

    restored = subprocess.run(
        ["bash", script],
        check=False,
        capture_output=True,
        text=True,
        env={**environment, "RESTORE_CONFIRMATION": "I_HAVE_VERIFIED_THE_TARGET_DATABASE"},
    )
    assert restored.returncode == 0, restored.stderr
    args = restore_args.read_text(encoding="utf-8")
    assert "--single-transaction" in args
    assert "--clean" in args
    assert "--dbname=studio_recovery" in args
    assert restore_input.read_text(encoding="utf-8") == "decrypted database dump"
