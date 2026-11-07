#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${PGSERVICE:?Set PGSERVICE to a protected libpq service definition}"
: "${PGPASSFILE:?Set PGPASSFILE to a protected password file}"
: "${PGDATABASE:?Set PGDATABASE to the explicit restore target}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the encrypted backup path}"
: "${AGE_IDENTITY_FILE:?Set AGE_IDENTITY_FILE to the private age identity file}"
: "${RESTORE_CONFIRMATION:?Set RESTORE_CONFIRMATION to the exact confirmation phrase}"

[[ "$RESTORE_CONFIRMATION" == "I_HAVE_VERIFIED_THE_TARGET_DATABASE" ]] || {
  echo "Refusing restore: explicit target-database confirmation is required" >&2
  exit 1
}
[[ -f "$BACKUP_FILE" && -f "$AGE_IDENTITY_FILE" && -f "$PGPASSFILE" ]] || {
  echo "Backup, age identity, or PGPASSFILE is missing" >&2
  exit 1
}
mode="$(stat -c '%a' "$PGPASSFILE")"
(( (8#$mode & 077) == 0 )) || { echo "PGPASSFILE must not be accessible by group/other" >&2; exit 1; }
mode="$(stat -c '%a' "$AGE_IDENTITY_FILE")"
(( (8#$mode & 077) == 0 )) || { echo "AGE_IDENTITY_FILE must not be accessible by group/other" >&2; exit 1; }
[[ "$PGDATABASE" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Unsafe PGDATABASE name" >&2; exit 1; }
command -v age >/dev/null
command -v pg_restore >/dev/null
command -v sha256sum >/dev/null
[[ -f "${BACKUP_FILE}.sha256" ]] || { echo "Backup checksum sidecar is missing" >&2; exit 1; }
(cd "$(dirname "$BACKUP_FILE")" && sha256sum --check "$(basename "${BACKUP_FILE}.sha256")")

echo "WARNING: restoring into database '$PGDATABASE' replaces conflicting objects."
age --decrypt --identity "$AGE_IDENTITY_FILE" "$BACKUP_FILE" |
  pg_restore --exit-on-error --single-transaction --clean --if-exists --no-owner --no-acl --dbname="$PGDATABASE"
echo "Restore command completed for database '$PGDATABASE'. Verify application health and row counts."
