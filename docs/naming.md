# Naming conventions

How the apps in this repo are named in code, docs, and builds.

## Apps

| Role | Folder | Product / purpose |
|------|--------|-------------------|
| Desktop client | `client_app/` | **FrogsWork**: sales invoicing UI |
| Account API | `account_api/` | Auth, Stripe, entitlements |
| Account API (dev) | `account_api/dev/` | Flask dev server, port 8787 |
| Account API (prod) | `account_api/worker/` | Cloudflare Worker, api.frogswork.com |
| Marketing site | `marketing_site/` | frogswork.com static pages |

## Desktop client (`client_app/`)

| Name | Meaning |
|------|---------|
| **FrogsWork** | User-facing product (`APP_BRAND_NAME` in `app_config.py`) |
| **`client_app/`** | Repo folder: desktop client |
| **`FrogsWork.exe`** | PyInstaller build output |
| **`%APPDATA%\FrogsWork\`** | User data (settings, invoices, entitlement cache) |

Env vars: `FROGSWORK_DEV_BROWSER`, `FROGSWORK_ONEFILE` (build). Account API URL: `DEFAULT_ACCOUNT_API_URL` in `app_config.py` or stored auth URL.

Integration is **HTTP only** via `client_app/account_client.py`.

## Account API (`account_api/`)

| Name | Meaning |
|------|---------|
| **`account_api/dev/`** | Flask dev server |
| **`account_api/worker/`** | Cloudflare Worker (production) |
| **D1 / SQLite** | User accounts and Stripe customer IDs |

## Build scripts

| Script | Builds |
|--------|--------|
| `client_app/build.ps1` | `client_app/` → `FrogsWork.exe` |
| `client_app/scripts/build_installer.ps1` | Inno Setup installer |
| `scripts/package_client_release.ps1` | Full release (exe + zip + manifest) |

Requirements: `client_app/requirements.txt`.
