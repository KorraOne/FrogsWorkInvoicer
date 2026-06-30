# FrogsWork

Monorepo for the **FrogsWork** desktop invoicing app, account API, and marketing site.

| App | Folder | Purpose |
|-----|--------|---------|
| **FrogsWork** (desktop client) | [`client_app/`](client_app/) | Sales invoicing UI, Stripe subscription |
| **Account API** | [`account_api/`](account_api/) | Auth, Stripe, entitlements (`dev/` Flask, `worker/` Cloudflare) |
| **Marketing site** | [`marketing_site/`](marketing_site/) | Static site (frogswork.com) + releases.json |

## Quick links

- Desktop app: [`client_app/README.md`](client_app/README.md) · [`docs/commercial/DEPLOY.md`](docs/commercial/DEPLOY.md)
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

Fresh dev environment (clear AppData + API db, then seed sample data):

```powershell
.\scripts\reset-dev.ps1 -Force -Seed -ResetSeed
```

## Repo layout

```
client_app/               FrogsWork desktop client + installer build
account_api/
  dev/                    Local Flask API (port 8787)
  worker/                 Production Cloudflare Worker (api.frogswork.com)
marketing_site/           Static site + wrangler.toml
scripts/                  Dev orchestration and release packaging
docs/commercial/          Operator docs
```

## Data

- User data: `%APPDATA%\FrogsWork\`
- Account integration is HTTP-only from `client_app/` to `api.frogswork.com`

Made by [KorraOne.com](https://korraone.com).
