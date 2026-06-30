# FrogsWork

Monorepo for the **FrogsWork** desktop invoicing app, account API, and marketing site.

| App | Folder | Purpose |
|-----|--------|---------|
| **FrogsWork** (desktop client) | [`client_app/`](client_app/) | Sales invoicing UI, Stripe subscription |
| **Account API** | [`workers/frogswork-api/`](workers/frogswork-api/) | Cloudflare Worker: auth, Stripe, entitlements (local dev: [`frogswork_api/`](frogswork_api/)) |
| **Marketing site** | [`marketing_site/`](marketing_site/) | Static site (frogswork.com) + releases.json |

## Quick links

- Desktop app: [`client_app/README.md`](client_app/README.md) · [`docs/commercial/DEPLOY.md`](docs/commercial/DEPLOY.md) · [billing rules](docs/commercial/billing-rules.md)
- Account API: [`workers/frogswork-api/README.md`](workers/frogswork-api/README.md)
- Marketing: [`marketing_site/README.md`](marketing_site/README.md)

## Build

```powershell
.\build_client.ps1
```

## Local dev

```powershell
.\scripts\start-dev.ps1 -DevBrowser
```

## Repo layout

```
client_app/               FrogsWork desktop client (Flask + pywebview)
workers/frogswork-api/    Production account API (Cloudflare Worker)
frogswork_api/            Local dev account API (Flask)
marketing_site/           Static site (frogswork.com) + releases.json
docs/commercial/          FrogsWork docs (billing, security, deploy, …)
```

## Data

- User data: `%APPDATA%\FrogsWork\`
- Account integration is HTTP-only from `client_app/` to `api.frogswork.com`

Made by [KorraOne.com](https://korraone.com).
