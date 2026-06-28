# FrogsWork marketing site

Static site at **https://frogswork.com**. Deployed via Cloudflare Worker **`frogswork-invoicer`** and root [`wrangler.toml`](../wrangler.toml).

Release zips: **https://downloads.frogswork.com** (R2 — not in git).

**Deploy / Pi:** [DEPLOY.md](../docs/commercial/DEPLOY.md) · [PI-SETUP.md](../billing_server/deploy/PI-SETUP.md)

## Pages

| Path | Purpose |
|------|---------|
| `/` | Home |
| `/pricing.html` | Pricing |
| `/download.html` | Latest release (`releases.json`) |
| `/privacy.html` | Privacy |
| `/terms.html` | Terms |

## Publish a release (Windows)

```powershell
.\scripts\package_client_release.ps1 -Version "1.0.0" -ReleaseNotes "Release note."
```

1. Upload zip to R2
2. Set `CLIENT_RELEASE_*` on Pi
3. Push `marketing_site/releases.json` to `main`

## Local preview

```powershell
cd marketing_site
python -m http.server 8088
```

## Cloudflare settings

| Setting | Value |
|---------|--------|
| Deploy command | `npx wrangler deploy` |
| Build command | *(none)* |
| Custom domain | `frogswork.com` |
