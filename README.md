# GrandparentsInvoicer

Monorepo with **three separate applications**. They share no Python imports. The commercial app was copied from the grandparents app and evolved independently.

| App | Folder | Purpose |
|-----|--------|---------|
| **Invoice App** (grandparents) | [`invoice_app/`](invoice_app/) | Personal/family GST invoicing, original scope |
| **FrogsWork** (desktop client) | [`client_app/`](client_app/) | Sales invoicing UI, talks to `billing_server/` |
| **Billing server** | [`billing_server/`](billing_server/) | KorraOne billing API (accounts, usage, platform fee invoices) |

## Quick links

- Grandparents app: [`invoice_app/README.md`](invoice_app/README.md) · agent context: [`docs/app-description.md`](docs/app-description.md)
- Commercial app: [`docs/commercial/DEPLOY.md`](docs/commercial/DEPLOY.md) · [naming](docs/commercial/naming.md) · [marketing site](marketing_site/README.md)
- Billing server: [`billing_server/README.md`](billing_server/README.md)

## Build

```powershell
# Grandparents Invoice App
.\build.ps1

# FrogsWork commercial desktop app
.\build_client.ps1

# Dev: billing server + commercial app
.\scripts\dev-test.ps1 -Action StartAll
```

## Repo layout

```
invoice_app/          Grandparents desktop app (Flask + PyInstaller)
client_app/      FrogsWork desktop client (Flask + pywebview + billing HTTP client)
billing_server/       Flask billing API (SQLite)
marketing_site/       Static site (frogswork.com) + releases.json; zips on downloads.frogswork.com
docs/
  app-description.md    Grandparents app, detailed agent/product context
  commercial/           FrogsWork docs (billing rules, security, brand, …)
scripts/dev-test.ps1  Dev harness for FrogsWork stack
build.ps1             Build grandparents exe
build_client.ps1      Build FrogsWork exe
requirements.txt      Invoice App dependencies
requirements-client.txt   FrogsWork client dependencies
```

## Isolation

- **No cross-imports** between `invoice_app/` and `client_app/`.
- AppData is separate: `%APPDATA%\InvoiceApp\` vs `%APPDATA%\FrogsWork\`.
- Billing integration is HTTP-only from `client_app/` to `billing_server/`.

Made by [KorraOne.com](https://korraone.com).
