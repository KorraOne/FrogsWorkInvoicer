# GrandparentsInvoicer

Monorepo with **three separate applications**. They share no Python imports. The commercial app was copied from the grandparents app and evolved independently.

| App | Folder | Purpose |
|-----|--------|---------|
| **Invoice App** (grandparents) | [`invoice_app/`](invoice_app/) | Personal/family GST invoicing, original scope |
| **FrogsWork** (desktop client) | [`client_app/`](client_app/) | Sales invoicing UI, Stripe subscription account API |
| **Account API** | [`workers/frogswork-api/`](workers/frogswork-api/) | Cloudflare Worker: auth, Stripe, entitlements (local dev: [`frogswork_api/`](frogswork_api/)) |

## Quick links

- Grandparents app: [`invoice_app/README.md`](invoice_app/README.md) · agent context: [`docs/app-description.md`](docs/app-description.md)
- Commercial app: [`docs/commercial/DEPLOY.md`](docs/commercial/DEPLOY.md) · [billing rules](docs/commercial/billing-rules.md) · [marketing site](marketing_site/README.md)
- Account API: [`workers/frogswork-api/README.md`](workers/frogswork-api/README.md)

## Build

```powershell
# Grandparents Invoice App
.\build.ps1

# FrogsWork commercial desktop app
.\build_client.ps1
```

## Repo layout

```
invoice_app/              Grandparents desktop app (Flask + PyInstaller)
client_app/               FrogsWork desktop client (Flask + pywebview)
workers/frogswork-api/    Production account API (Cloudflare Worker)
frogswork_api/            Local dev account API (Flask)
archive/billing_server/   Retired usage-billing Pi stack (reference only)
marketing_site/           Static site (frogswork.com) + releases.json
docs/commercial/          FrogsWork docs (billing, security, deploy, …)
```

## Isolation

- **No cross-imports** between `invoice_app/` and `client_app/`.
- AppData is separate: `%APPDATA%\InvoiceApp\` vs `%APPDATA%\FrogsWork\`.
- Account integration is HTTP-only from `client_app/` to `api.frogswork.com`.

Made by [KorraOne.com](https://korraone.com).
