#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${PGSERVICE:?Set PGSERVICE to a protected libpq service definition}"
: "${PGPASSFILE:?Set PGPASSFILE to a protected password file}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${BACKUP_DIR:?Set BACKUP_DIR}"
: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT to an age public recipient}"

command -v pg_dump >/dev/null
command -v age >/dev/null
[[ -f "$PGPASSFILE" ]] || { echo "PGPASSFILE does not exist" >&2; exit 1; }
mode="$(stat -c '%a' "$PGPASSFILE")"
(( (8#$mode & 077) == 0 )) || { echo "PGPASSFILE must not be accessible by group/other" >&2; exit 1; }
[[ "$PGDATABASE" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Unsafe PGDATABASE name" >&2; exit 1; }

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
base="${PGDATABASE}-${timestamp}.dump"
plain_tmp="$(mktemp)"
encrypted_tmp="$(mktemp "${BACKUP_DIR}/.backup.XXXXXX")"
cleanup() { rm -f "$plain_tmp" "$encrypted_tmp"; }
trap cleanup EXIT

pg_dump --format=custom --compress=9 --no-owner --no-acl --file="$plain_tmp"
age --recipient "$BACKUP_AGE_RECIPIENT" --output "$encrypted_tmp" "$plain_tmp"
destination="${BACKUP_DIR}/${base}.age"
mv "$encrypted_tmp" "$destination"
chmod 600 "$destination"
sha256sum "$destination" > "${destination}.sha256"
chmod 600 "${destination}.sha256"
printf 'Encrypted backup created: %s\n' "$destination"

if [[ "${BACKUP_RETENTION_DAYS:-0}" =~ ^[0-9]+$ ]] && (( ${BACKUP_RETENTION_DAYS:-0} > 0 )); then
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${PGDATABASE}-*.dump.age" \
    -mtime "+$((BACKUP_RETENTION_DAYS - 1))" -delete
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${PGDATABASE}-*.dump.age.sha256" \
    -mtime "+$((BACKUP_RETENTION_DAYS - 1))" -delete
fi
