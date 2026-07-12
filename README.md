# FrogsWork

Monorepo for the **FrogsWork** desktop invoicing app, account API, and marketing site.

| App | Folder | Purpose |
|-----|--------|---------|
| **FrogsWork** (desktop client) | [`client_app/`](client_app/) | Sales invoicing UI, Stripe subscription |
| **Account API** | [`account_api/`](account_api/) | Auth, Stripe, entitlements, cloud documents (`dev/` Flask, `worker/` Cloudflare) |
| **Marketing site** | [`marketing_site/`](marketing_site/) | Static site (frogswork.com) + releases.json |
| **Mobile PWA** | [`client_web/`](client_web/) | Cloud-tier mobile client (app.frogswork.com, planned) |

**Platform overview:** [`docs/PLATFORM-ARCHITECTURE.md`](docs/PLATFORM-ARCHITECTURE.md)

## Quick links

- Desktop app: [`client_app/README.md`](client_app/README.md) · [`docs/DEPLOY.md`](docs/DEPLOY.md)
- Account API: [`account_api/README.md`](account_api/README.md)
- Marketing: [`marketing_site/README.md`](marketing_site/README.md)

## Build

```powershell
.\client_app\build.ps1
```

## Local dev

```powershell
.\scripts\start-dev.ps1 -DevBrowser
```

**PWA + cloud API** (mobile UI against Worker):

```powershell
.\scripts\start-pwa-dev.ps1
# In browser console on http://127.0.0.1:8090:
# localStorage.setItem('frogswork_api','http://127.0.0.1:8787')
```

Deploy PWA: `cd client_web && npx wrangler pages deploy . --project-name frogswork-app`

Fresh dev environment (clear AppData + API db, then seed sample data):

```powershell
.\scripts\reset-dev.ps1 -Force -Seed -ResetSeed
```

## Repo layout

```
client_app/               FrogsWork desktop client + installer build
client_web/               Mobile PWA (Cloud tier, offline cache)
account_api/
  dev/                    Local Flask API (port 8787)
  worker/                 Production Cloudflare Worker (api.frogswork.com)
marketing_site/           Static site + wrangler.toml
scripts/                  Dev orchestration and release packaging
docs/                     Operator + architecture docs
```

## Data

- User data: `%APPDATA%\FrogsWork\`
- Account integration is HTTP-only from `client_app/` to `api.frogswork.com`

Made by [KorraOne.com](https://korraone.com).
