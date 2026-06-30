# Naming conventions

How the apps in this repo are named in code, docs, and builds.

## Apps

| Role | Folder | Product / purpose |
|------|--------|-------------------|
| Grandparents app | `invoice_app/` | **Invoice App**: personal/family invoicing |
| Desktop client | `client_app/` | **FrogsWork**: sales invoicing UI |
| Account API | `workers/frogswork-api/` | Auth, Stripe, entitlements (production) |
| Local dev API | `frogswork_api/` | Same routes as Worker, Flask on port 8787 |

There are **no Python imports** between `invoice_app/` and `client_app/`.

## Desktop client (`client_app/`)

| Name | Meaning |
|------|---------|
| **FrogsWork** | User-facing product (`APP_BRAND_NAME` in `app_config.py`) |
| **`client_app/`** | Repo folder: desktop client |
| **`FrogsWork.exe`** | PyInstaller build output |
| **`%APPDATA%\FrogsWork\`** | User data (settings, invoices, entitlement cache) |

Env vars: `FROGSWORK_DEV_BROWSER`, `FROGSWORK_ONEFILE` (build). Account API URL: `DEFAULT_ACCOUNT_API_URL` in `app_config.py` or stored auth URL.

Integration is **HTTP only** via `client_app/account_client.py`.

## Account API

| Name | Meaning |
|------|---------|
| **`workers/frogswork-api/`** | Cloudflare Worker (production `api.frogswork.com`) |
| **`frogswork_api/`** | Flask dev server |
| **D1 / SQLite** | User accounts and Stripe customer IDs |

Retired usage billing: [`archive/billing_server/`](../../archive/billing_server/).

## Grandparents app (`invoice_app/`)

| Name | Meaning |
|------|---------|
| **Invoice App** | User-facing name |
| **`invoice_app/`** | Repo folder |
| **`InvoiceApp.exe`** | Build output |
| **`%APPDATA%\InvoiceApp\`** | User data |

No billing, accounts, or FrogsWork branding.

## Build scripts (repo root)

| Script | Builds |
|--------|--------|
| `build.ps1` | `invoice_app/` → `InvoiceApp.exe` |
| `build_client.ps1` | `client_app/` → `FrogsWork.exe` |

Requirements: `requirements-client.txt` (FrogsWork), `requirements.txt` (Invoice App).
