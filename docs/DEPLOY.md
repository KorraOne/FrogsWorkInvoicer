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

## First-time D1 setup (required once)

R2 and the marketing Worker can work without D1, but **accounts, login, telemetry, and `/admin` need D1**. If [`account_api/worker/wrangler.toml`](../account_api/worker/wrangler.toml) still has `database_id = "00000000-0000-0000-0000-000000000000"`, D1 is not wired up.

**Automated (interactive terminal, after `npx wrangler login`):**

```powershell
.\scripts\setup-d1-production.ps1
```

This script: finds or creates `frogswork-account`, patches `wrangler.toml`, applies [`account_api/schema.sql`](../account_api/schema.sql) to **remote** D1, deploys the Worker, and smoke-tests `/health` + `/telemetry/heartbeat`.

**Manual equivalent:**

```powershell
cd account_api/worker
npm install
npx wrangler login
npx wrangler d1 create frogswork-account    # or copy existing ID from dashboard
# Paste database_id into wrangler.toml (replace 00000000-…)
npx wrangler d1 execute frogswork-account --remote --file=../schema.sql
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put JWT_SECRET
npx wrangler secret put ADMIN_PASSWORD
npm run deploy
```

Skip D1 setup only if `wrangler.toml` already has a **real** `database_id` and `SELECT name FROM sqlite_master` shows `users` and `installs`.

---

## Deploy account API (Worker)

After D1 is live, redeploy when code changes:

```powershell
cd account_api/worker
npm run deploy
curl https://api.frogswork.com/health
```

Set **`ADMIN_PASSWORD`** for the operator analytics dashboard at `https://api.frogswork.com/admin` (HTTP Basic auth). JSON summary: `/admin/api/summary`.

Set release metadata as Worker vars or secrets: `CLIENT_RELEASE_VERSION`, `CLIENT_RELEASE_URL`, `CLIENT_RELEASE_SHA256`, `CLIENT_RELEASE_NOTES`.

Custom domain: attach **api.frogswork.com** to the Worker in Cloudflare.

---

## Ship a desktop release

**2.0.0** is the subscription-model release (replaces usage-based billing). **R2** can stay as-is from an earlier deploy; ensure **D1** is set up first (see above).

**Automated release (after D1 + `wrangler login`):**

```powershell
.\scripts\deploy-release-2.0.0.ps1
```

Prompts for R2 bucket name if not passed: `-R2Bucket "your-bucket"`. Builds, uploads to R2, sets `CLIENT_RELEASE_*` in `wrangler.toml`, deploys API + marketing.

### Build only (Windows, repo root)

Requires **Inno Setup 6**. See [`client_app/installer/README.md`](../client_app/installer/README.md).

```powershell
.\scripts\package_client_release.ps1 -Version "2.0.0" -ReleaseNotes "Replaces usage-based billing with a simple monthly or annual subscription. Free trial: 20 invoices or `$20,000 ex GST before subscribe."
```

The script updates `marketing_site/releases.json` with SHA256 hashes after the build. Confirm `client_app/app_config.py` shows `APP_VERSION = "2.0.0"`.

### Deploy checklist

#### 1. Upload to R2 (`downloads.frogswork.com`)

| File | Purpose |
|------|---------|
| `FrogsWork-2.0.0-setup.exe` | Public download |
| `FrogsWork-2.0.0-win64.zip` | In-app updates |

#### 2. Update Worker release metadata

Set on the account API Worker:

| Variable | Example |
|----------|---------|
| `CLIENT_RELEASE_VERSION` | `2.0.0` |
| `CLIENT_RELEASE_URL` | `https://downloads.frogswork.com/FrogsWork-2.0.0-win64.zip` |
| `CLIENT_RELEASE_SHA256` | from package script output |
| `CLIENT_RELEASE_NOTES` | Same subscription-billing note as above |

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

### Stuck on an old version after a failed update

If the app closed during an update but did not reopen, or Settings still shows an older version:

1. Download the latest installer from [frogswork.com/download.html](https://frogswork.com/download.html) and run it (your data in `%APPDATA%\FrogsWork\` is kept).
2. Or delete `dismissed_version` from `%APPDATA%\FrogsWork\update_state.json`, then **Settings → App update → Check again → Update now**.
3. Check `%APPDATA%\FrogsWork\update.log` for robocopy errors.

Versions before **2.2.1** may need the manual installer once; **2.2.1+** includes a more reliable in-app updater (retries, logging, auto-restart).

---

## Stripe (subscribe flow)

The desktop app opens **Stripe Payment Links** baked in at build time. The account API validates checkout and subscriptions (needs Stripe secrets on the Worker).

### 1. Stripe Dashboard

1. **Products** — monthly `$12.99`, annual `$129.90` (test mode for beta).
2. **Payment links** — create one monthly and one annual link.
3. **Customer portal** — enable (used for manage billing).

### 2. Local config (not committed)

```powershell
copy client_app\production.env.example client_app\production.env
# Edit production.env — paste Payment Link URLs + STRIPE_SECRET_KEY (sk_test_… for beta)
```

### 3. API Worker secrets + Payment Link redirects

```powershell
.\scripts\setup-stripe-production.ps1
```

This sets `STRIPE_SECRET_KEY`, `JWT_SECRET`, `STRIPE_WEBHOOK_SECRET` on `frogswork-api` and points both Payment Links to:

`http://127.0.0.1:5000/account/stripe/return?session_id={CHECKOUT_SESSION_ID}`

The packaged app runs a local server on port 5000 — Stripe redirects back to the running app after payment.

### 4. Rebuild and deploy the desktop app

Payment links are **baked into the installer** at build time (`production.env` required):

```powershell
.\scripts\deploy-release-2.0.0.ps1 -Version "2.1.2" -R2Bucket "frogswork-invoicer-releases" -ReleaseNotes "Enable Stripe subscribe flow."
```

### 5. Smoke test

- [ ] Subscribe page shows Pay monthly / Pay annually (not "Not configured yet")
- [ ] Stripe checkout opens in browser; test card `4242 4242 4242 4242`
- [ ] After payment, browser hits localhost return page; app continues to set password
- [ ] Settings → Your account shows active subscription

See also [`account_api/worker/README.md`](../account_api/worker/README.md).

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
