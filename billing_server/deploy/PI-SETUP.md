# Raspberry Pi setup from scratch

Billing API for **api.frogswork.com**. Run these steps in order on a **fresh Pi** (Raspberry Pi OS 64-bit recommended).

## Directory layout (chosen paths)

| Path | What |
|------|------|
| `/home/frogswork/frogswork/` | Git repo root (`KorraOne/FrogsWorkInvoicer`) |
| `/home/frogswork/frogswork/billing_server/` | Flask app, `.venv`, `billing.db`, PDFs |
| `/etc/frogswork/billing.env` | Production secrets (not in git) |
| `/home/frogswork/backups/frogswork-billing/` | Nightly DB backups |
| `/home/frogswork/.cloudflared/` | Tunnel login + credentials |

The app listens on **`127.0.0.1:8008` only** (8008 avoids conflict with other local services on 8080). The public internet reaches it via **Cloudflare Tunnel**, not open router ports.

---

## Part 1 — SSH into the Pi

From your Windows PC:

```powershell
ssh pi@<pi-ip-address>
```

Or use Raspberry Pi Imager hostname, Tailscale IP, etc.

Update the OS (recommended once):

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

SSH back in after reboot.

---

## Part 2 — Bootstrap script (automated)

Copy the repo to the Pi **or** clone only the bootstrap script. Easiest if the repo is public on GitHub:

```bash
# As your normal Pi user (with sudo)
cd ~
git clone https://github.com/KorraOne/FrogsWorkInvoicer.git frogswork-tmp
cd frogswork-tmp/billing_server/deploy
chmod +x pi-bootstrap.sh
sudo GIT_REPO=https://github.com/KorraOne/FrogsWorkInvoicer.git ./pi-bootstrap.sh
```

**Private repo?** Use SSH deploy key or HTTPS token:

```bash
sudo GIT_REPO=git@github.com:KorraOne/FrogsWorkInvoicer.git ./pi-bootstrap.sh
```

The script creates user `frogswork`, clones to `/home/frogswork/frogswork`, installs Python deps, writes `/etc/frogswork/billing.env` with random JWT/Flask secrets, and installs systemd units.

---

## Part 3 — Edit secrets and release info

```bash
sudo nano /etc/frogswork/billing.env
```

**Required before start:**

| Variable | Example / action |
|----------|------------------|
| `ADMIN_PASSWORD` | Replace `CHANGE_ME_BEFORE_START` with a strong password |
| `HOST` | Keep `127.0.0.1` |
| `BASE_URL` | Keep `https://api.frogswork.com` |

**After R2 zip upload (v1.0.0):**

```env
CLIENT_RELEASE_VERSION=1.0.0
CLIENT_RELEASE_URL=https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip
CLIENT_RELEASE_SHA256=6781632ba41eaea68d45208b69319978fbd9baab6955317ece03ad95de55b114
CLIENT_RELEASE_NOTES=First public release.
```

Save (Ctrl+O, Enter, Ctrl+X).

---

## Part 4 — Start billing service

```bash
sudo systemctl start frogswork-billing
sudo systemctl status frogswork-billing
curl -s http://127.0.0.1:8008/health
```

Expected: `{"status":"ok"}` (may include `client_release_version` if set).

**Admin UI (local only for now):**

From your **Windows PC** (new terminal, keep Pi running):

```powershell
ssh -L 8008:127.0.0.1:8008 pi@<pi-ip>
```

Browser: http://127.0.0.1:8008/admin — login with `ADMIN_PASSWORD`.

---

## Part 5 — Cloudflare Tunnel (api.frogswork.com)

On the Pi as user **frogswork**:

```bash
sudo -u frogswork -i
```

### 5a. Install cloudflared

```bash
# Pi 4 / 5 64-bit (aarch64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

For **32-bit** Pi OS use `cloudflared-linux-arm.deb` instead.

### 5b. Login and create tunnel

```bash
cloudflared tunnel login
# Browser opens — pick frogswork.com zone

cloudflared tunnel create frogswork-api
# Note the tunnel UUID and credentials file path
```

### 5c. DNS route

```bash
cloudflared tunnel route dns frogswork-api api.frogswork.com
```

### 5d. Config file

```bash
mkdir -p ~/.cloudflared
cp ~/frogswork/billing_server/deploy/cloudflared-config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml
```

Set `credentials-file` to the JSON path printed by `tunnel create` (often `~/.cloudflared/<uuid>.json`). You can rename or symlink to `frogswork-api.json` to match the example.

Test:

```bash
cloudflared tunnel run frogswork-api
```

In another terminal from your **laptop**:

```bash
curl -s https://api.frogswork.com/health
```

### 5e. Run tunnel as a service

Follow Cloudflare’s “run as a service on Linux” doc, or:

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

(Exact command may vary by install method — use Cloudflare dashboard **Zero Trust → Networks → Tunnels** if CLI service install is unclear.)

---

## Part 6 — Verify end-to-end

From your laptop:

```bash
curl -s https://api.frogswork.com/health
curl -s https://api.frogswork.com/releases/latest
```

Install FrogsWork on Windows from https://frogswork.com/download.html — sign-in / account flows should hit the Pi API.

---

## Part 7 — Push releases.json (marketing site)

On your **Windows dev PC** (already done locally):

Commit and push `marketing_site/releases.json` to `main` so frogswork.com/download shows v1.0.0.

---

## Updating later

**Billing server code:**

```bash
sudo -u frogswork git -C /home/frogswork/frogswork pull
sudo systemctl restart frogswork-billing
```

**New desktop release:** rebuild zip on Windows, upload R2, update `CLIENT_RELEASE_*` in `billing.env`, restart billing.

---

## Troubleshooting

| Problem | Check |
|---------|--------|
| `systemctl status frogswork-billing` failed | `journalctl -u frogswork-billing -n 50` |
| Health works on Pi, not public | Tunnel running? `cloudflared tunnel list` |
| Git clone private repo fails | SSH key for `frogswork` user on GitHub |
| Admin 404 on api.frogswork.com | Expected — use SSH `-L 8008:127.0.0.1:8008` |

Full deploy doc: [DEPLOY.md](../../docs/commercial/DEPLOY.md)
