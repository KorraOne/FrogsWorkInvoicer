# FrogsWork marketing site

Static site at **https://frogswork.com**. Deployed via Cloudflare Worker **`frogswork-invoicer`** and [`wrangler.toml`](wrangler.toml).

**Installers and update zips** live on **https://downloads.frogswork.com** (R2, not deployed with this site):

- **`FrogsWork-x.y.z-setup.exe`** — linked from `/download.html` via `releases.json` → `download_path`
- **`FrogsWork-x.y.z-win64.zip`** — in-app updates via account API `CLIENT_RELEASE_*` vars

**Deploy:** [DEPLOY.md](../docs/commercial/DEPLOY.md) · [STRIPE_SETUP.md](../docs/commercial/STRIPE_SETUP.md)

## Pages

| Path | Purpose |
|------|---------|
| `/` | Home |
| `/pricing.html` | Pricing (subscribe happens in the desktop app) |
| `/download.html` | Latest release (`releases.json`) |
| `/support.html` | Support hub |
| `/issues.html` | Frequent issues + troubleshooting |
| `/contact.html` | Contact support |
| `/privacy.html` | Privacy |
| `/terms.html` | Terms |

## Layout

Public HTML lives at the **site root** (flat URLs — no build step). `downloads/` is local packaging only and excluded from deploy.

## Publish a release (Windows)

```powershell
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "Release note."
```

Then:

1. Upload **setup.exe** and **zip** to R2 (`downloads.frogswork.com`)
2. Set `CLIENT_RELEASE_*` on the account API Worker (zip URL + SHA256)
3. Commit `marketing_site/releases.json` and deploy: `cd marketing_site; npx wrangler deploy`

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
