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

## Stripe (Local / Cloud plans + email-first signup)

Account creation runs on **frogswork.com** (`/account/signup.html` → `/account/subscribe.html` → Stripe Checkout → `/account/return.html`). The API uses **Checkout Sessions** (`POST /checkout/create-session`) with four price IDs. CORS must allow `https://frogswork.com` (and `www`).

### 1. Stripe Dashboard / script

```powershell
python account_api\dev\setup_stripe_prices.py --grandfather-existing
```

Creates Local ($9.99/mo, $99/yr) and Cloud ($14.99/mo, $149/yr) prices with `storage_tier` metadata. Tags legacy $12.99/$129.90 prices as `local` when using `--grandfather-existing`.

### 2. Local config (not committed)

```powershell
copy client_app\production.env.example client_app\production.env
# Paste STRIPE_SECRET_KEY + STRIPE_PRICE_LOCAL_MONTHLY|ANNUAL + STRIPE_PRICE_CLOUD_* from script output
```

Copy the same `STRIPE_PRICE_*` values into `account_api/worker/wrangler.toml` `[vars]` (or Worker secrets).

### 3. API Worker secrets

```powershell
.\scripts\setup-stripe-production.ps1
```

Sets `STRIPE_SECRET_KEY`, `JWT_SECRET`, `STRIPE_WEBHOOK_SECRET` on `frogswork-api`. Configure Stripe webhook → `https://api.frogswork.com/webhooks/stripe` for `checkout.session.completed`.

**Coupons / promo codes:** Checkout shows Stripe’s promotion code field. Scope coupons to FrogsWork products only — see [`STRIPE-COUPONS.md`](STRIPE-COUPONS.md). List product IDs: `python account_api\dev\setup_stripe_prices.py --list-catalog`.

### 4. Deploy marketing site

```powershell
.\scripts\sync-marketing-account-config.ps1
cd marketing_site
npx wrangler deploy
```

### 5. Verify

- [ ] `frogswork.com/account/signup.html` — email + password form
- [ ] `frogswork.com/account/subscribe.html` — Local vs Cloud cards + monthly/annual toggle
- [ ] `POST /auth/signup` returns `signup_token` for pending accounts

### 6. Smoke test

- [ ] Signup → choose Local or Cloud → Stripe checkout; test card `4242 4242 4242 4242`
- [ ] After payment, return page → success (account active; no separate password step)
- [ ] Desktop: Sign in opens web; returns to app via `127.0.0.1:5000/account/auth/callback`
- [ ] PWA (Cloud): Sign in → token handoff at `app.frogswork.com/#auth/callback` → dashboard
- [ ] PWA Local subscriber: sign-in shows upgrade gate (expected)
- [ ] PWA Cloud paid: **Send** delivers invoice email via Resend
- [ ] Desktop Local paid: **Send automatically** delivers PDF (relay API)
- [ ] Forgot password / verification emails arrive (Resend)
- [ ] Local subscriber: Upgrade to Cloud opens web checkout; after pay, migrate wizard works
- [ ] Settings → Your account shows active subscription and storage tier (desktop)

See also [`account_api/worker/README.md`](../account_api/worker/README.md).

---

## Mobile PWA (`app.frogswork.com`)

| Setting | Value |
|---------|--------|
| Source | [`client_web_v2/`](../client_web_v2/) (v2 rebuild; legacy in `client_web_legacy/`) |
| Build | `cd client_web_v2` then `npm install` and `npm run build` |
| Deploy | `npx wrangler pages deploy dist --project-name frogswork-app` |
| Custom domain | `app.frogswork.com` in Cloudflare Pages dashboard |
| API | PWA v2 uses `/mobile/v1/*` (cloud-only); desktop keeps `/documents/*` |
| Access | **Cloud subscribers only** — Local plans are desktop-only |
| Offline | **Deferred** — online-first; no service worker |

In-app email/password sign-in is primary. Web handoff: `frogswork.com/account/login.html?next=pwa` → `?pwa_auth=1&access_token=…`.

Deploy API worker after changing [`mobile.js`](../account_api/worker/src/mobile.js): `cd account_api\worker` then `npm run deploy`.

See [`PWA-V2-AUDIT.md`](PWA-V2-AUDIT.md) for v1 debt notes and migration rationale.

---

## D1 migrations (after schema changes)

```powershell
cd account_api\worker
npx wrangler d1 execute frogswork-account --remote --file=..\migrations\006_checkout_promo_settings.sql
npx wrangler d1 execute frogswork-account --remote --file=..\migrations\007_auth_extensions.sql
npx wrangler d1 execute frogswork-account --remote --file=..\migrations\008_cloud_documents_tables.sql
npx wrangler d1 execute frogswork-account --remote --file=..\migrations\009_email_outbox_invoice_key.sql
npm run deploy
```

Migration `008` creates `guest_workspaces`, `doc_*`, and `email_outbox` if missing (safe to re-run). Use it instead of `003` when `storage_tier` already exists.

---

## Email (Resend — invoices + transactional)

Set on the API worker:

```powershell
cd account_api\worker
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put EMAIL_FROM   # e.g. FrogsWork <invoices@frogswork.com>
npm run deploy
```

1. Verify **frogswork.com** in Resend (SPF + DKIM in Cloudflare DNS).
2. `EMAIL_FROM` can be any address `@frogswork.com` once the domain is verified.

**Send behaviour:**

| User | Auto email | Manual send |
|------|------------|-------------|
| Local paid (desktop) | Yes — `POST /email/invoices/:n/send` relay | Copy email page |
| Cloud paid (PWA) | Yes — documents outbox + Resend | N/A |

Without Resend secrets, dev logs print email payloads to the Worker console.

---

## Stripe Customer Portal

Enable in Stripe Dashboard → Settings → Customer portal. Allow customers to switch between all four FrogsWork prices (Local/Cloud × monthly/annual). Desktop and PWA open `portal_url` from `GET /entitlements`.

---

## BETA80 auto-apply (admin)

1. Create `BETA80` promotion code in Stripe (see [`STRIPE-COUPONS.md`](STRIPE-COUPONS.md)).
2. `python account_api\dev\setup_stripe_prices.py --lookup-promo-beta80` → set `STRIPE_PROMO_BETA80` in `wrangler.toml` or `wrangler secret put`.
3. Toggle **Auto-apply BETA80 at checkout** at `https://api.frogswork.com/admin`.

Optional URL promo: `subscribe.html?promo=BETA80` (used when admin default is off).

---

## Marketing site (Cloudflare)

| Setting | Value |
|---------|--------|
| Config | [`marketing_site/wrangler.toml`](../marketing_site/wrangler.toml) |
| Deploy | `cd marketing_site` then `npx wrangler deploy` |

Binaries on R2, not in git.

Unlisted remote user test: `https://frogswork.com/user-test.html` (not in nav).

---

## Remote user testing (optional R2 video uploads)

Tester page: **`https://frogswork.com/user-test`** (unlisted). Submissions are stored in D1; **video is optional** and uploads to R2 prefix `user-tests/` when provided. Enable/disable intake and download submissions at **`https://api.frogswork.com/admin`** → User testing section.

### One-time Cloudflare setup (operator)

**Secrets are not committed.** Use `wrangler secret put` or the Worker dashboard — not `client_app/production.env`.

1. **Bucket** — reuse **`frogswork-invoicer-releases`** (same as installer uploads). No new bucket unless you prefer one.

2. **R2 API token** — Dashboard → R2 → **Manage R2 API Tokens** → Create (Object Read & Write). Then:

```powershell
cd account_api\worker
npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
npx wrangler secret put R2_ACCOUNT_ID
npm run deploy
```

3. **R2 CORS** (only needed if testers upload video) — bucket → Settings → CORS policy:

```json
[
  {
    "AllowedOrigins": ["https://frogswork.com"],
    "AllowedMethods": ["PUT", "HEAD"],
    "AllowedHeaders": ["Content-Type", "Content-Length"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

4. **D1 migration** (once, after pulling user-test tables):

```powershell
cd account_api\worker
npx wrangler d1 execute frogswork-account --remote --file=..\migrations\2026-07-02_user_test.sql
```

5. **Deploy** marketing + API:

```powershell
cd account_api\worker
npm run deploy
cd ..\..\marketing_site
npx wrangler deploy
```

6. **Enable intake** — `https://api.frogswork.com/admin` → check **Accepting submissions**. Default is **OFF**.

7. **Smoke test** — submit **answers only** (no video) and confirm in admin; optionally submit a small test video (needs R2 CORS); delete test rows.

Share **`https://frogswork.com/user-test`** with testers only while intake is ON.

---

## Marketing video guides (R2)

Public page: **`https://frogswork.com/guides.html`**. Videos are hosted on the same R2 bucket as installers, under prefix **`videos/`**, and referenced from [`marketing_site/videos.json`](../marketing_site/videos.json).

### R2 layout

```
videos/
  walkthrough.mp4
  install.mp4
  setup-business.mp4
  …
  posters/
    walkthrough.jpg
    install.jpg
    …
```

Public URLs: `https://downloads.frogswork.com/videos/<file>` (custom domain on the releases bucket).

### Upload a video

Set **`Content-Type: video/mp4`** on upload. Example with AWS CLI (S3-compatible endpoint for R2):

```powershell
aws s3 cp install.mp4 s3://frogswork-invoicer-releases/videos/install.mp4 --content-type video/mp4 --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com
aws s3 cp posters/install.jpg s3://frogswork-invoicer-releases/videos/posters/install.jpg --content-type image/jpeg --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Poster JPGs: grab a frame at ~2s with ffmpeg, e.g. `ffmpeg -ss 2 -i install.mp4 -frames:v 1 posters/install.jpg`.

### Publish on the site

1. Upload MP4 and poster to R2.
2. In `marketing_site/videos.json`, set `"published": true` for that entry (all required fields must be present; see [`docs/MARKETING-VIDEOS.md`](MARKETING-VIDEOS.md)).
3. Deploy marketing: `cd marketing_site` then `npx wrangler deploy`.

The site can ship before videos exist: unpublished entries show **Video coming soon** with step lists still visible.

### Recording demo data

Fictional AppData for screen recordings (no real customers or invoices):

```powershell
cd client_app
python seed_marketing_demo.py --reset
```

See [`docs/MARKETING-VIDEOS.md`](MARKETING-VIDEOS.md) for the full shot list.

---

## Related docs

- [naming.md](naming.md) · [brand.md](brand.md)
- [account_api/worker/README.md](../account_api/worker/README.md) — Stripe Dashboard, webhooks
- [marketing_site/README.md](../marketing_site/README.md)
