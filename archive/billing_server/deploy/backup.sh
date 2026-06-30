#!/usr/bin/env bash
# Backup billing.db and platform invoice PDFs. Run from cron on the Pi.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/home/frogswork/backups/frogswork-billing}"
APP_ROOT="${APP_ROOT:-/home/frogswork/frogswork/billing_server}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${DEST}"

if [[ -f "${APP_ROOT}/billing.db" ]]; then
  cp -a "${APP_ROOT}/billing.db" "${DEST}/"
fi

if [[ -d "${APP_ROOT}/platform_invoices" ]]; then
  cp -a "${APP_ROOT}/platform_invoices" "${DEST}/"
fi

# Keep last 14 daily backups
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort | head -n -14 | xargs -r rm -rf

echo "Backup written to ${DEST}"
