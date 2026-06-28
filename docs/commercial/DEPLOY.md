# FrogsWork production deploy

Reference for **frogswork.com**, **api.frogswork.com**, and Pi hosting. For a fresh Pi, start with [`billing_server/deploy/PI-SETUP.md`](../../billing_server/deploy/PI-SETUP.md).

## Production layout

| Host | Role |
|------|------|
| `frogswork.com` | Marketing (Cloudflare Worker + `wrangler.toml` → `marketing_site/`) |
| `downloads.frogswork.com` | Release zips (R2) |
| `api.frogswork.com` | Billing API + `/releases/latest` (Pi, port **8008**, tunnel `frogswork-api`) |

```
Browser          → frogswork.com              (marketing + releases.json)
Download         → downloads.frogswork.com    (R2 zip)
Desktop app      → api.frogswork.com          (auth, usage, update metadata)
Operator admin   → localhost:8008 via SSH     (/admin — not public)
User data        → %APPDATA%\FrogsWork\       (on each PC)
```

**Pi paths:** repo `/home/frogswork/frogswork/` · secrets `/etc/frogswork/billing.env` · billing listens **`127.0.0.1:8008`** (8008 avoids clash with other local apps on 8080).

**Two tunnels on one Pi:** existing `pi` tunnel (`my-webapp`) is unchanged. FrogsWork uses a separate **`cloudflared-frogswork.service`** (user `frogswork`, tunnel `frogswork-api`). Do **not** run `sudo cloudflared service install` — that conflicts with the existing setup.

---

## Fresh Pi (summary)

1. `sudo ./billing_server/deploy/pi-bootstrap.sh` — see [PI-SETUP.md](../../billing_server/deploy/PI-SETUP.md)
2. Edit `/etc/frogswork/billing.env` (`PORT=8008`, secrets, `CLIENT_RELEASE_*`)
3. `sudo systemctl start frogswork-billing`
4. Create `frogswork-api` tunnel; install `cloudflared-frogswork.service`
5. Verify `curl https://api.frogswork.com/health`

---

## Ship a desktop release

On Windows (repo root):

```powershell
.\scripts\package_client_release.ps1 -Version "1.0.0" -ReleaseNotes "Your release note."
```

Then:

1. Upload `client_app\dist\FrogsWork-x.y.z-win64.zip` to R2
2. Set `CLIENT_RELEASE_*` in `/etc/frogswork/billing.env` on Pi → `sudo systemctl restart frogswork-billing`
3. Push `marketing_site/releases.json` to `main` (Wrangler redeploys frogswork.com)

Details: [RELEASE.md](RELEASE.md)

---

## In-app updates (when you ship 1.0.1+)

Not required to test before v1.0.0 launch. When ready:

1. Bump `APP_VERSION` in `client_app/app_config.py`
2. Run `package_client_release.ps1` with new version
3. Upload zip to R2; update `CLIENT_RELEASE_*` on Pi
4. Push `releases.json`

Installed apps call `GET /releases/latest`, download from R2, verify SHA256, replace install folder. AppData unchanged.

---

## Marketing site (Cloudflare)

| Setting | Value |
|---------|--------|
| Project | `frogswork-invoicer` (Workers static assets) |
| Deploy command | `npx wrangler deploy` |
| Config | Root [`wrangler.toml`](../../wrangler.toml) → `marketing_site/` |

Custom domain: **Domains** → `frogswork.com`. Zips live on R2, not in git.

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

## Clean-machine test checklist

- [ ] https://frogswork.com/download.html shows current version
- [ ] Zip downloads from R2
- [ ] Extract to `%LOCALAPPDATA%\Programs\FrogsWork\`, run exe
- [ ] Welcome flow, create invoice (free tier, offline OK)
- [ ] Optional: account sign-in, Settings → Your account shows server OK
- [ ] `curl https://api.frogswork.com/releases/latest` returns JSON

Update flow: test when shipping **1.0.1** (see [RELEASE.md](RELEASE.md)).

---

## Related docs

- [PI-SETUP.md](../../billing_server/deploy/PI-SETUP.md) — Pi from scratch
- [RELEASE.md](RELEASE.md) — install layout, update mechanics
- [marketing_site/README.md](../../marketing_site/README.md)
- [operator-admin.md](operator-admin.md)
- [security-risk-model.md](security-risk-model.md)
