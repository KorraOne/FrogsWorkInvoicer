# FrogsWork marketing site

Static site at **https://frogswork.com**. Deployed via Cloudflare Worker **`frogswork-invoicer`** and [`wrangler.toml`](wrangler.toml).

**Installers and update zips** live on **https://downloads.frogswork.com** (R2, not deployed with this site):

- **`FrogsWork-x.y.z-setup.exe`** — linked from `/download.html` via `releases.json` → `download_path`
- **`FrogsWork-x.y.z-win64.zip`** — in-app updates via account API `CLIENT_RELEASE_*` vars

**Marketing videos** also live on R2 under `videos/` and are listed in [`videos.json`](videos.json). See [MARKETING-VIDEOS.md](../docs/MARKETING-VIDEOS.md).

**Deploy:** [DEPLOY.md](../docs/DEPLOY.md)

## Pages

| Path | Purpose |
|------|---------|
| `/` | Home |
| `/pricing.html` | Pricing + subscribe CTAs |
| `/account/subscribe.html` | Stripe Payment Link checkout |
| `/account/return.html` | Stripe redirect; polls API |
| `/account/create.html` | Set password after payment |
| `/account/login.html` | Sign in (`?next=pwa` or `?next=desktop`) |
| `/account/success.html` | Post-register / post-login next steps |
| `/download.html` | Latest release (`releases.json`) |
| `/guides.html` | Video guides (walkthrough + tutorials) |
| `/support.html` | Support hub |
| `/issues.html` | Frequent issues + troubleshooting |
| `/contact.html` | Contact support |
| `/privacy.html` | Privacy policy |
| `/privacy.html` | Privacy |
| `/terms.html` | Terms |

## Account pages (local dev)

```powershell
cd marketing_site
python -m http.server 8080
```

1. Start API: `.\scripts\start-pwa-dev.ps1` (or account API on `:8787`)
2. Set payment links in browser console (or run `.\scripts\sync-marketing-account-config.ps1` after filling `production.env`):

   ```javascript
   localStorage.setItem('stripe_link_monthly', 'https://buy.stripe.com/test_...');
   localStorage.setItem('stripe_link_annual', 'https://buy.stripe.com/test_...');
   ```

3. Point Stripe Payment Link redirects to `http://127.0.0.1:8080/account/return.html?session_id={CHECKOUT_SESSION_ID}` (`configure_payment_links.py`).

Config: [`js/account/config.js`](js/account/config.js) — `PAYMENT_LINKS` synced from `client_app/production.env` via [`scripts/sync-marketing-account-config.ps1`](../scripts/sync-marketing-account-config.ps1).

## Layout

Public HTML lives at the **site root** (flat URLs — no build step). `downloads/` is local packaging only and excluded from deploy.

Brand assets: [`assets/brand/`](assets/brand/) (logo, favicon). Video manifest: [`videos.json`](videos.json), rendered by [`js/guides.js`](js/guides.js).

## Publish a release (Windows)

```powershell
.\scripts\package_client_release.ps1 -Version "2.0.0" -ReleaseNotes "Replaces usage-based billing with subscription."
```

Then:

1. Upload **setup.exe** and **zip** to R2 (`downloads.frogswork.com`)
2. Set `CLIENT_RELEASE_*` on the account API Worker (zip URL + SHA256)
3. Commit `marketing_site/releases.json` and deploy: `cd marketing_site; npx wrangler deploy`

## GA4 events

Measurement ID: `js/analytics-config.js` → `FW_GA4_MARKETING_ID`. Loader and helpers: [`js/analytics.js`](js/analytics.js).

| Event | Trigger | Conversion? |
|-------|---------|-------------|
| `page_view` | Automatic on load | No |
| `signup_click` | Create account links (`data-fw-signup`) | No |
| `sign_up` | Successful account create (`js/account/signup.js`) | No |
| `begin_checkout` | Stripe checkout URL returned (`subscribe.js`) | No |
| `purchase` | Paid confirmed (`return.js` / upgrade in `subscribe.js`) | **Yes — only key event** |
| `open_app_click` | Links to app.frogswork.com (`data-fw-open-app`) | No |
| `download_click` | Download for Windows CTAs (`data-fw-download`) | No |
| `video_play` / `video_progress` | Guides players (`guides.js`) | No |
| `support_contact_click` | mailto on contact (`data-fw-support`) | No |

In GA4 Admin → Events, mark **`purchase` only** as a key event. Funnel exploration: `signup_click` → `sign_up` → `begin_checkout` → `purchase`.

## Local preview

```powershell
cd marketing_site
python -m http.server 8088
```

## Cloudflare

| Setting | Value |
|---------|--------|
| Deploy | `npx wrangler deploy` |
| Build | *(none — static assets)* |
| Domain | `frogswork.com` |

The `downloads/` folder is for local packaging only; it is excluded from Worker deploy (see `wrangler.toml`).
