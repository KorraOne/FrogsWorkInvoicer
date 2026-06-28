# Raspberry Pi setup

Billing API for **api.frogswork.com**. SSH as **`pi`** (or your usual admin user). The **`frogswork`** Linux user runs the app but has **no password and no sudo** — use `sudo -u frogswork -i` when you need that account.

## Paths

| Path | Purpose |
|------|---------|
| `/home/frogswork/frogswork/` | Git repo |
| `/home/frogswork/frogswork/billing_server/` | App, `.venv`, `billing.db` |
| `/etc/frogswork/billing.env` | Secrets |
| `/home/frogswork/.cloudflared/` | FrogsWork tunnel config |
| `/home/frogswork/backups/frogswork-billing/` | Nightly backups |

Billing binds **`127.0.0.1:8008`** only. Public access is via tunnel **`frogswork-api`** → `api.frogswork.com`.

If this Pi already runs another Cloudflare tunnel (e.g. `my-webapp` under user `pi`), leave it alone. FrogsWork uses a **second** tunnel and **`cloudflared-frogswork.service`**.

---

## 1. Bootstrap

```bash
cd ~
git clone https://github.com/KorraOne/FrogsWorkInvoicer.git frogswork-tmp
cd frogswork-tmp/billing_server/deploy
chmod +x pi-bootstrap.sh
sudo GIT_REPO=https://github.com/KorraOne/FrogsWorkInvoicer.git ./pi-bootstrap.sh
```

Private repo: use `GIT_REPO=git@github.com:KorraOne/FrogsWorkInvoicer.git` and a deploy key for user `frogswork`.

---

## 2. Secrets and release metadata

```bash
sudo nano /etc/frogswork/billing.env
```

| Variable | Production value |
|----------|------------------|
| `HOST` | `127.0.0.1` |
| `PORT` | `8008` |
| `BASE_URL` | `https://api.frogswork.com` |
| `ADMIN_PASSWORD` | Strong operator password |
| `CLIENT_RELEASE_*` | Set after first zip is on R2 (version, URL, SHA256, notes) |

```bash
sudo systemctl start frogswork-billing
curl -s http://127.0.0.1:8008/health
```

---

## 3. Cloudflare tunnel (frogswork-api)

### Install cloudflared (as `pi`, once)

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

### Create tunnel (as `frogswork`, no sudo inside this shell)

```bash
sudo -u frogswork -i

cloudflared tunnel login
cloudflared tunnel create frogswork-api
cloudflared tunnel route dns frogswork-api api.frogswork.com

mkdir -p ~/.cloudflared
cp ~/frogswork/billing_server/deploy/cloudflared-config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml
```

Set `credentials-file` to the JSON from `tunnel create` (e.g. `~/.cloudflared/<uuid>.json`). Confirm ingress:

```yaml
  - hostname: api.frogswork.com
    service: http://127.0.0.1:8008
```

Test (foreground — Ctrl+C when done):

```bash
cloudflared tunnel run frogswork-api
```

From laptop: `curl https://api.frogswork.com/health`

### Persistent service (as `pi`)

Do **not** use `sudo cloudflared service install` if `pi` already has `cloudflared.service`.

```bash
exit   # leave frogswork shell if still in it

sudo cp /home/frogswork/frogswork/billing_server/deploy/cloudflared-frogswork.service /etc/systemd/system/
# Or copy from frogswork-tmp if repo not yet at /home/frogswork/frogswork

sudo systemctl daemon-reload
sudo systemctl enable cloudflared-frogswork
sudo systemctl start cloudflared-frogswork
sudo systemctl status cloudflared-frogswork
```

---

## 4. Admin UI (SSH only)

From Windows:

```powershell
ssh -L 8008:127.0.0.1:8008 pi@<pi-ip>
```

http://127.0.0.1:8008/admin

---

## 5. Verify

```bash
curl -s https://api.frogswork.com/health
curl -s https://api.frogswork.com/releases/latest
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Cloudflare error 1033 | `cloudflared-frogswork` not running — `sudo systemctl status cloudflared-frogswork` |
| `frogswork is not in the sudoers file` | Expected — run `sudo` as **`pi`**, not inside frogswork shell |
| Health OK on Pi, fails publicly | Tunnel config still on wrong port or service down |
| Port conflict on 8080 | Billing must use **8008**; other apps can keep 8080 |

Full reference: [DEPLOY.md](../../docs/commercial/DEPLOY.md)
