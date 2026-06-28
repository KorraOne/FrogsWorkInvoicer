# FrogsWork marketing site

Static site for **https://frogswork.com** — deployed via Cloudflare Worker **`frogswork-invoicer`** and root [`wrangler.toml`](../wrangler.toml).

**Deploy checklist:** [`docs/commercial/DEPLOY.md`](../docs/commercial/DEPLOY.md)

## Pages

| Path | Purpose |
|------|---------|
| `/` | Home, features, CTA |
| `/pricing.html` | Free tier and platform fees |
| `/download.html` | Latest zip (from `releases.json`) |
| `/privacy.html` | Privacy policy |
| `/terms.html` | Terms of use |

## Distribution vs update metadata

| Role | Host |
|------|------|
| **Zip file** (bytes) | `downloads.frogswork.com` (Cloudflare R2) |
| **Update check** (version, URL, SHA256) | `api.frogswork.com` → `GET /releases/latest` |
| **Marketing** | `frogswork.com` (Cloudflare Pages) |

The desktop app asks the **billing API** whether an update exists, then downloads the zip from the URL in that response (R2).

## Publish a release

From repo root on Windows:

```powershell
.\scripts\package_client_release.ps1 -Version "1.0.0" -ReleaseNotes "First public release."
```

Then follow steps 14–16 in [DEPLOY.md](../docs/commercial/DEPLOY.md): upload zip to R2, set `CLIENT_RELEASE_*` on Pi, push `releases.json` to Pages.

## Local preview

```powershell
cd marketing_site
python -m http.server 8088
```

Open http://127.0.0.1:8088/download.html

## Deploy

**Cloudflare Pages:** output directory `marketing_site`, custom domain `frogswork.com`.

Do **not** commit large zips. Only push HTML/CSS/JS and `releases.json`.
