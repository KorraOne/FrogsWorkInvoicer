#!/usr/bin/env bash
# FrogsWork billing server — first-time Raspberry Pi bootstrap
#
# Run on a fresh Pi as a user with sudo (typically the default pi/ubuntu user):
#   curl -fsSL ...  OR  copy this file to the Pi and:
#   chmod +x pi-bootstrap.sh
#   sudo GIT_REPO=https://github.com/KorraOne/FrogsWorkInvoicer.git ./pi-bootstrap.sh
#
# What it does:
#   - Creates Linux user `frogswork`
#   - Clones repo to /home/frogswork/frogswork
#   - Python venv + pip install
#   - /etc/frogswork/billing.env from template (generates JWT/Flask secrets)
#   - Installs systemd units + backup cron
#
# After this script: edit billing.env (ADMIN_PASSWORD, CLIENT_RELEASE_*, SMTP),
# start services, set up cloudflared (see PI-SETUP.md).

set -euo pipefail

GIT_REPO="${GIT_REPO:-https://github.com/KorraOne/FrogsWorkInvoicer.git}"
APP_USER="frogswork"
REPO_DIR="/home/${APP_USER}/frogswork"
ENV_FILE="/etc/frogswork/billing.env"
BACKUP_DIR="/home/${APP_USER}/backups/frogswork-billing"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo GIT_REPO=... ./pi-bootstrap.sh"
  exit 1
fi

echo "==> Installing packages (git, python3, venv)..."
apt-get update -qq
apt-get install -y git python3 python3-venv python3-pip curl

if ! id "${APP_USER}" &>/dev/null; then
  echo "==> Creating user ${APP_USER}..."
  adduser --disabled-password --gecos "" "${APP_USER}"
else
  echo "==> User ${APP_USER} already exists."
fi

mkdir -p /etc/frogswork
chown root:root /etc/frogswork
chmod 700 /etc/frogswork

mkdir -p "${BACKUP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "/home/${APP_USER}/backups"

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  echo "==> Cloning ${GIT_REPO} -> ${REPO_DIR}"
  sudo -u "${APP_USER}" git clone "${GIT_REPO}" "${REPO_DIR}"
else
  echo "==> Repo already exists at ${REPO_DIR} (skipping clone)."
fi

echo "==> Python venv + requirements..."
sudo -u "${APP_USER}" bash -c "
  cd '${REPO_DIR}/billing_server'
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "==> Creating ${ENV_FILE}..."
  JWT_SECRET="$(openssl rand -hex 32)"
  FLASK_SECRET="$(openssl rand -hex 32)"
  cp "${REPO_DIR}/billing_server/deploy/production.env.example" "${ENV_FILE}"
  sed -i "s/JWT_SECRET=REPLACE_WITH_OPENSSL_RAND_HEX_32/JWT_SECRET=${JWT_SECRET}/" "${ENV_FILE}"
  sed -i "s/FLASK_SECRET_KEY=REPLACE_WITH_OPENSSL_RAND_HEX_32/FLASK_SECRET_KEY=${FLASK_SECRET}/" "${ENV_FILE}"
  sed -i "s/ADMIN_PASSWORD=REPLACE_WITH_STRONG_OPERATOR_PASSWORD/ADMIN_PASSWORD=CHANGE_ME_BEFORE_START/" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  chown root:root "${ENV_FILE}"
  echo ""
  echo "*** IMPORTANT: set ADMIN_PASSWORD and CLIENT_RELEASE_* in ${ENV_FILE} ***"
else
  echo "==> ${ENV_FILE} already exists (not overwritten)."
fi

echo "==> Installing systemd units..."
cp "${REPO_DIR}/billing_server/deploy/frogswork-billing.service" /etc/systemd/system/
cp "${REPO_DIR}/billing_server/deploy/frogswork-auto-billing.service" /etc/systemd/system/
cp "${REPO_DIR}/billing_server/deploy/frogswork-auto-billing.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable frogswork-billing frogswork-auto-billing.timer

chmod +x "${REPO_DIR}/billing_server/deploy/backup.sh"

CRON_LINE="15 2 * * * ${REPO_DIR}/billing_server/deploy/backup.sh"
(sudo -u "${APP_USER}" crontab -l 2>/dev/null | grep -F backup.sh) || \
  (sudo -u "${APP_USER}" bash -c "(crontab -l 2>/dev/null; echo '${CRON_LINE}') | crontab -")

mkdir -p "${REPO_DIR}/billing_server/platform_invoices"
chown -R "${APP_USER}:${APP_USER}" "${REPO_DIR}"

echo ""
echo "=============================================="
echo "Bootstrap complete."
echo ""
echo "Next steps (see billing_server/deploy/PI-SETUP.md):"
echo "  1. sudo nano ${ENV_FILE}"
echo "     - Set ADMIN_PASSWORD"
echo "     - Set CLIENT_RELEASE_VERSION, URL, SHA256, NOTES"
echo "  2. sudo systemctl start frogswork-billing"
echo "  3. curl -s http://127.0.0.1:8080/health"
echo "  4. Install cloudflared + tunnel api.frogswork.com"
echo "=============================================="
