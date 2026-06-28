# FrogsWork production deploy

Exact order to go from zero to a live product: marketing site, downloads, billing API on a Pi, and the first Windows release.

**Domain map (production):**

| Host | Role |
|------|------|
| `frogswork.com` | Marketing site (Home, Pricing, Download, Privacy, Terms) |
| `downloads.frogswork.com` | Release zip files (Cloudflare R2 — large binaries) |
| `api.frogswork.com` | Billing API + `/releases/latest` (Pi + Cloudflare Tunnel) |

Admin UI (`/admin`) is **not** on a public URL. Use SSH port-forward from your laptop (see step 12).

---

## Before you start

- [ ] Domain **`frogswork.com`** in Cloudflare (DNS active).
- [ ] Raspberry Pi on your network, Raspberry Pi OS updated, SSH working.
- [ ] Cloudflare account with **Zero Trust / Tunnel** enabled.
- [ ] Windows dev PC with this repo, Python 3.11+, PowerShell.
- [ ] KorraOne business details ready (ABN, bank, address) for platform invoices.
- [ ] SMTP credentials if you want automatic platform invoice email.

Generate two secrets on your laptop (save in a password manager):

```bash
openssl rand -hex 32   # JWT_SECRET
openssl rand -hex 32   # FLASK_SECRET_KEY
```

Pick a strong `ADMIN_PASSWORD` for the operator admin UI.

---

## Phase A — Cloudflare DNS (15 min)

Do this first so certificates propagate while you set up the Pi.

### 1. Marketing apex (Workers static assets + Git)

Repo includes [`wrangler.toml`](../../wrangler.toml) at the root. Cloudflare project **`frogswork-invoicer`** should use:

| Setting | Value |
|---------|--------|
| Git repository | `KorraOne/FrogsWorkInvoicer` (or your fork) |
| Production branch | `main` |
| Build command | *(none)* |
| Deploy command | `npx wrangler deploy` |
| Root directory | `/` |

1. Push `wrangler.toml` to `main` (triggers a deploy), or **Deployments → Retry deployment**.
2. Confirm the `*.workers.dev` URL shows the marketing home page.
3. In the Worker project → **Domains** → add **`frogswork.com`** and optionally **`www.frogswork.com`**.

Alternative: **Pages → Upload assets** if you prefer not to use Wrangler (see [marketing_site/README.md](../../marketing_site/README.md)).

### 2. Download hosting (R2)

PyInstaller zips are usually **>25 MB**, too large for Pages git deploy.

1. **R2** → Create bucket `frogswork-releases` (private is fine).
2. **Public access** → Allow public reads via custom domain **`downloads.frogswork.com`** (Cloudflare walks you through DNS).
3. Note the public URL pattern: `https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip`.

You will upload zips here in Phase D.

### 3. API tunnel hostname

Do not create an A record for `api` yet — **cloudflared** will create it in step 10.

---

## Phase B — Raspberry Pi billing server (45–60 min)

### 4. Create Linux user and directories

On the Pi (SSH as default user, then):

```bash
sudo adduser --disabled-password --gecos "" frogswork
sudo mkdir -p /etc/frogswork
sudo chown root:root /etc/frogswork
sudo chmod 700 /etc/frogswork
sudo mkdir -p /home/frogswork/backups/frogswork-billing
sudo chown -R frogswork:frogswork /home/frogswork/backups
```

### 5. Clone repo and Python venv

As user `frogswork`:

```bash
sudo -u frogswork -i
git clone <your-repo-url> ~/frogswork
cd ~/frogswork/billing_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
exit
```

Replace `<your-repo-url>` with your actual remote. Pull-based updates later: `sudo -u frogswork git -C /home/frogswork/frogswork pull`.

### 6. Production environment file

On the Pi:

```bash
sudo cp /home/frogswork/frogswork/billing_server/deploy/production.env.example /etc/frogswork/billing.env
sudo chmod 600 /etc/frogswork/billing.env
sudo nano /etc/frogswork/billing.env
```

Set at minimum:

- `JWT_SECRET`, `FLASK_SECRET_KEY`, `ADMIN_PASSWORD`
- `KORRAONE_*` when ready to send real invoices
- `SMTP_*` if using auto email
- Leave `CLIENT_RELEASE_*` empty until Phase D

**Keep `HOST=127.0.0.1`.** The API must not listen on the LAN/WAN directly.

### 7. Install systemd services

```bash
sudo cp /home/frogswork/frogswork/billing_server/deploy/frogswork-billing.service /etc/systemd/system/
sudo cp /home/frogswork/frogswork/billing_server/deploy/frogswork-auto-billing.service /etc/systemd/system/
sudo cp /home/frogswork/frogswork/billing_server/deploy/frogswork-auto-billing.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable frogswork-billing frogswork-auto-billing.timer
sudo systemctl start frogswork-billing
```

Check:

```bash
curl -s http://127.0.0.1:8080/health
# {"status":"ok"}
```

### 8. Daily backup cron

```bash
sudo chmod +x /home/frogswork/frogswork/billing_server/deploy/backup.sh
sudo crontab -u frogswork -e
```

Add:

```cron
15 2 * * * /home/frogswork/frogswork/billing_server/deploy/backup.sh
```

---

## Phase C — Public API tunnel (20 min)

### 9. Install cloudflared on Pi

Follow [Cloudflare docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) for `arm64`/`armhf`, or:

```bash
# Example Debian/Bookworm — verify latest package from Cloudflare
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

### 10. Create tunnel for api.frogswork.com

As user `frogswork`:

```bash
cloudflared tunnel login
cloudflared tunnel create frogswork-api
cloudflared tunnel route dns frogswork-api api.frogswork.com
```

Copy example config:

```bash
mkdir -p ~/.cloudflared
cp ~/frogswork/billing_server/deploy/cloudflared-config.yml.example ~/.cloudflared/config.yml
# Edit credentials-file path if cloudflared put the json elsewhere
nano ~/.cloudflared/config.yml
```

Install as system service (Cloudflare’s `cloudflared service install` or systemd unit from their docs). Start tunnel.

### 11. Verify public API

From your laptop (not the Pi):

```bash
curl -s https://api.frogswork.com/health
# {"status":"ok"}
```

If this fails, fix tunnel/DNS before continuing.

---

## Phase D — First client release (Windows dev PC)

Do this **after** step 11 succeeds so the built exe points at a live API.

### 12. Operator admin (SSH — not public)

From your laptop:

```bash
ssh -L 8080:127.0.0.1:8080 frogswork@<pi-hostname-or-tailscale-ip>
```

Open http://127.0.0.1:8080/admin and log in with `ADMIN_PASSWORD`.

See [operator-admin.md](operator-admin.md) for billing workflows.

### 13. Set version and build

On Windows, in repo root:

1. Edit `client_app/app_config.py`:
   - `APP_VERSION = "1.0.0"` (your release version)
   - `APP_BRAND_URL = "https://frogswork.com"` *(already default after domain update)*

2. Package release:

```powershell
.\scripts\package_client_release.ps1 `
  -Version "1.0.0" `
  -BillingUrl "https://api.frogswork.com" `
  -MarketingSiteUrl "https://frogswork.com" `
  -DownloadHost "https://downloads.frogswork.com" `
  -ReleaseNotes "First public release."
```

This will:

- Build `FrogsWork.exe` with API URL baked in
- Create zip + SHA256
- Update `marketing_site/releases.json`
- Copy zip to `marketing_site/downloads/` (local copy for reference)
- Print `CLIENT_RELEASE_*` lines for the Pi

### 14. Upload zip to R2

Upload `client_app\dist\FrogsWork-1.0.0-win64.zip` to bucket `frogswork-releases` so it is available at:

`https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip`

Verify in browser (download starts).

### 15. Enable updates on billing server

On the Pi, edit `/etc/frogswork/billing.env`:

```env
CLIENT_RELEASE_VERSION=1.0.0
CLIENT_RELEASE_URL=https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip
CLIENT_RELEASE_SHA256=<from package script output>
CLIENT_RELEASE_NOTES=First public release.
```

```bash
sudo systemctl restart frogswork-billing
curl -s https://api.frogswork.com/releases/latest
```

### 16. Deploy marketing site

1. Commit and push `marketing_site/` changes (including updated `releases.json`). Use a **gitignore-safe** approach: do **not** commit multi‑MB zips; only `releases.json` and HTML/CSS/JS.
2. Cloudflare Pages redeploys from git, or upload the `marketing_site/` folder manually.
3. Open https://frogswork.com — check Home, Pricing, Download.
4. Download page should show version **1.0.0** and link to the R2 zip (via full URL in `releases.json`).

---

## Phase E — Smoke test (15 min)

### 17. Fresh install test

On a clean Windows PC (or VM):

1. Download from https://frogswork.com/download.html
2. Extract to `%LOCALAPPDATA%\Programs\FrogsWork\`
3. Run `FrogsWork.exe` — welcome flow, create a test invoice under free tier
4. Optional: create account, confirm `https://api.frogswork.com` calls succeed (Settings → Your account)

### 18. Update path test (optional before ship)

1. Bump `APP_VERSION` to `1.0.1` locally, build `1.0.0` stays installed on test PC
2. Upload `1.0.1` zip to R2, update `CLIENT_RELEASE_*` on Pi
3. Open installed app while online — banner appears → **Update now** → app restarts on new version; AppData intact

---

## Ongoing operations

### Ship a new version

1. Bump `APP_VERSION` in `client_app/app_config.py`
2. Run `package_client_release.ps1` with new `-Version` and `-BillingUrl https://api.frogswork.com`
3. Upload zip to R2
4. Update `CLIENT_RELEASE_*` in `/etc/frogswork/billing.env` → `sudo systemctl restart frogswork-billing`
5. Push updated `marketing_site/releases.json` (Pages redeploys)

### Pi code updates (billing server only)

```bash
sudo -u frogswork git -C /home/frogswork/frogswork pull
sudo systemctl restart frogswork-billing
```

### Platform invoices

- Automatic: `frogswork-auto-billing.timer` (daily) + SMTP in env
- Manual: SSH admin tunnel → `/admin` → Generate, or `python run_billing_job.py` on Pi

### Backups

- Nightly `backup.sh` cron under user `frogswork`
- Copy `/home/frogswork/backups/` off-Pi periodically

---

## Quick reference — who serves what

```
User browser     → frogswork.com              (Pages: marketing + releases.json)
User download    → downloads.frogswork.com    (R2: zip bytes)
Desktop app      → api.frogswork.com          (Pi tunnel: auth, usage, /releases/latest)
Operator admin   → localhost:8080 via SSH     (/admin — not public)
User data        → %APPDATA%\FrogsWork\       (on each PC — never on your servers)
```

---

## Related docs

- [RELEASE.md](RELEASE.md) — install layout, in-app update mechanics
- [marketing_site/README.md](../../marketing_site/README.md) — site structure
- [security-risk-model.md](security-risk-model.md) — threat model and checklist
- [operator-admin.md](operator-admin.md) — admin UI workflows
- [billing_server/deploy/README.md](../../billing_server/deploy/README.md) — Pi file list
