# FrogsWork production deploy

Reference for **frogswork.com**, **api.frogswork.com**, and release hosting.

## Production layout

| Host | Role |
|------|------|
| `frogswork.com` | Marketing (Cloudflare Worker → `marketing_site/`) |
| `downloads.frogswork.com` | Release **setup.exe** + **update zip** (R2) |
| `api.frogswork.com` | Account API: auth, Stripe, entitlements, `/releases/latest` (Cloudflare Worker) |

```
Browser (new install) → frogswork.com/download.html → setup.exe (R2)
Browser (manifest)    → frogswork.com/releases.json
In-app update         → api.frogswork.com/releases/latest → zip (R2)
Desktop app           → api.frogswork.com (auth, checkout, entitlements)
User data             → %APPDATA%\FrogsWork\ (on each PC)
Program files         → %LOCALAPPDATA%\Programs\FrogsWork\ (on each PC)
```

**Local dev API:** [`account_api/dev/server.py`](../account_api/dev/server.py) on `http://127.0.0.1:8787`.

**Production API:** [`account_api/worker/`](../account_api/worker/) — Stripe setup in [`account_api/worker/README.md`](../account_api/worker/README.md).

---

## Deploy account API (Worker)

```powershell
cd account_api/worker
npm install
npx wrangler d1 execute frogswork-account --remote --file=../schema.sql
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put JWT_SECRET
npm run deploy
curl https://api.frogswork.com/health
```

Set release metadata as Worker vars or secrets: `CLIENT_RELEASE_VERSION`, `CLIENT_RELEASE_URL`, `CLIENT_RELEASE_SHA256`, `CLIENT_RELEASE_NOTES`.

Custom domain: attach **api.frogswork.com** to the Worker in Cloudflare.

---

## Ship a desktop release

### Build (Windows, repo root)

Requires **Inno Setup 6**. See [`client_app/installer/README.md`](../client_app/installer/README.md).

```powershell
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "Your release note."
```

### Deploy checklist

#### 1. Upload to R2 (`downloads.frogswork.com`)

| File | Purpose |
|------|---------|
| `FrogsWork-1.1.0-setup.exe` | Public download |
| `FrogsWork-1.1.0-win64.zip` | In-app updates |

#### 2. Update Worker release metadata

Set `CLIENT_RELEASE_*` on the Worker (zip URL + SHA256 from package script), then redeploy or update vars.

```bash
curl -s https://api.frogswork.com/releases/latest
```

#### 3. Deploy marketing site

Update `marketing_site/releases.json`, commit, push, then from `marketing_site/`: `npx wrangler deploy`.

#### 4. Smoke test

- [ ] Download page shows correct version
- [ ] Fresh install: trial invoicing offline
- [ ] Trial limit → account + subscribe flow (Stripe test card `4242…`)
- [ ] Settings → Your account → subscription verified
- [ ] In-app update from older build

---

## Marketing site (Cloudflare)

| Setting | Value |
|---------|--------|
| Config | [`marketing_site/wrangler.toml`](../marketing_site/wrangler.toml) |
| Deploy | `cd marketing_site` then `npx wrangler deploy` |

Binaries on R2, not in git.

---

## Related docs

- [naming.md](naming.md) · [brand.md](brand.md)
- [account_api/worker/README.md](../account_api/worker/README.md) — Stripe Dashboard, webhooks
- [marketing_site/README.md](../marketing_site/README.md)
