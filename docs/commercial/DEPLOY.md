# FrogsWork production deploy

Reference for **frogswork.com**, **api.frogswork.com**, and Pi hosting. For a fresh Pi, start with [`billing_server/deploy/PI-SETUP.md`](../../billing_server/deploy/PI-SETUP.md).

## Production layout

| Host | Role |
|------|------|
| `frogswork.com` | Marketing (Cloudflare Worker + `wrangler.toml` → `marketing_site/`) |
| `downloads.frogswork.com` | Release **setup.exe** + **update zip** (R2) |
| `api.frogswork.com` | Billing API + `/releases/latest` (Pi, port **8008**, tunnel `frogswork-api`) |

```
Browser (new install) → frogswork.com/download.html → setup.exe (R2)
Browser (manifest)    → frogswork.com/releases.json
In-app update         → api.frogswork.com/releases/latest → zip (R2)
Desktop app           → api.frogswork.com (auth, usage)
Operator admin        → localhost:8008 via SSH (/admin — not public)
User data             → %APPDATA%\FrogsWork\ (on each PC)
Program files         → %LOCALAPPDATA%\Programs\FrogsWork\ (on each PC)
```

**Pi paths:** repo `/home/frogswork/frogswork/` · secrets `/etc/frogswork/billing.env` · billing listens **`127.0.0.1:8008`**.

**Two tunnels on one Pi:** existing `pi` tunnel (`my-webapp`) is unchanged. FrogsWork uses **`cloudflared-frogswork.service`** (user `frogswork`, tunnel `frogswork-api`). Do **not** run `sudo cloudflared service install` — that conflicts with the existing setup.

---

## Fresh Pi (summary)

1. `sudo ./billing_server/deploy/pi-bootstrap.sh` — see [PI-SETUP.md](../../billing_server/deploy/PI-SETUP.md)
2. Edit `/etc/frogswork/billing.env` (`PORT=8008`, secrets, `CLIENT_RELEASE_*`)
3. `sudo systemctl start frogswork-billing`
4. Create `frogswork-api` tunnel; install `cloudflared-frogswork.service`
5. Verify `curl https://api.frogswork.com/health`

---

## Ship a desktop release

### Build (Windows, repo root)

Requires **Inno Setup 6** for the marketing installer. See [RELEASE.md](RELEASE.md).

```powershell
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "Your release note."
```

Script prints setup + zip paths and both SHA256 hashes.

### Deploy checklist

Do these in order:

#### 1. Upload to R2 (`downloads.frogswork.com`)

Upload **both** files from `client_app\dist\` (or `marketing_site\downloads\`):

| File | Purpose |
|------|---------|
| `FrogsWork-1.1.0-setup.exe` | Public download (new installs) |
| `FrogsWork-1.1.0-win64.zip` | In-app updates |

Use the Cloudflare dashboard or `wrangler r2 object put` — same bucket you already use for downloads.

#### 2. Update Pi release metadata

SSH to the Pi and edit `/etc/frogswork/billing.env`. **In-app updates use the zip**, not the setup exe:

```env
CLIENT_RELEASE_VERSION=1.1.0
CLIENT_RELEASE_URL=https://downloads.frogswork.com/FrogsWork-1.1.0-win64.zip
CLIENT_RELEASE_SHA256=ed7e6bd2ae7ebd1afcecb20e64b94fc66b51c131a6f90e5e1660c24c77ced928
CLIENT_RELEASE_NOTES=Windows installer, uninstall PDF export, API connectivity fixes.
```

Replace version, URL, SHA256, and notes for each release (hashes come from the package script output).

```bash
sudo systemctl restart frogswork-billing
curl -s https://api.frogswork.com/health
# Expect: "client_release_version":"1.1.0"
curl -s https://api.frogswork.com/releases/latest
```

#### 3. Deploy marketing site

Commit and push `marketing_site/releases.json` to `main`, then deploy:

```powershell
cd c:\Users\Repti\Desktop\Code\GrandparentsInvoicer
git add marketing_site/releases.json
git commit -m "Release 1.1.0"
git push
npx wrangler deploy
```

Or rely on your usual Cloudflare Pages/Workers pipeline if it auto-deploys on push.

#### 4. Smoke test

- [ ] https://frogswork.com/download.html shows **1.1.0** and downloads setup.exe
- [ ] Setup installs to `%LOCALAPPDATA%\Programs\FrogsWork\` and app launches
- [ ] Welcome flow, create invoice (free tier, offline OK)
- [ ] Settings → Your account → server shows OK (when signed in)
- [ ] `curl https://api.frogswork.com/releases/latest` matches Pi env
- [ ] Optional: on an older install, update banner → **Update now** → restarts on 1.1.0

Details: [RELEASE.md](RELEASE.md)

---

## In-app updates

1. Bump `APP_VERSION` in `client_app/app_config.py`
2. Run `package_client_release.ps1` with new version
3. Upload **zip** (and new **setup.exe**) to R2
4. Update `CLIENT_RELEASE_*` on Pi (zip URL + zip SHA256)
5. Push `releases.json` (`download_path` = setup, `sha256` = zip)

Installed apps call `GET /releases/latest`, download the zip from R2, verify SHA256, replace the install folder. AppData unchanged.

---

## Marketing site (Cloudflare)

| Setting | Value |
|---------|--------|
| Project | `frogswork-invoicer` (Workers static assets) |
| Deploy command | `npx wrangler deploy` |
| Config | Root [`wrangler.toml`](../../wrangler.toml) → `marketing_site/` |

Custom domain: **Domains** → `frogswork.com`. Binaries live on R2, not in git.

---

## Operator admin

From Windows:

```powershell
ssh -L 8008:127.0.0.1:8008 pi@<pi-ip>
```

http://127.0.0.1:8008/admin — see [operator-admin.md](operator-admin.md)

---

## Ongoing Pi maintenance

```bash
# Billing code update
sudo -u frogswork git -C /home/frogswork/frogswork pull
sudo systemctl restart frogswork-billing

# Check services
sudo systemctl status frogswork-billing cloudflared-frogswork

# Logs
journalctl -u frogswork-billing -n 50
journalctl -u cloudflared-frogswork -n 50
```

Backups: nightly cron from bootstrap → `/home/frogswork/backups/frogswork-billing/`

---

## Related docs

- [PI-SETUP.md](../../billing_server/deploy/PI-SETUP.md) — Pi from scratch
- [RELEASE.md](RELEASE.md) — install layout, update mechanics, Inno installer
- [installer/README.md](../../installer/README.md) — Inno Setup script
- [marketing_site/README.md](../../marketing_site/README.md)
- [operator-admin.md](operator-admin.md)
- [security-risk-model.md](security-risk-model.md)
