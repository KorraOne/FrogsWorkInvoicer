# Naming conventions

How the three apps in this repo are named in code, docs, and builds.

## Three apps

| Role | Folder | Product / purpose |
|------|--------|-------------------|
| Grandparents app | `invoice_app/` | **Invoice App**: personal/family invoicing (unchanged original) |
| Desktop client | `client_app/` | **FrogsWork**: sales invoicing UI |
| Billing API | `billing_server/` | KorraOne billing backend (accounts, usage, platform fees) |

There are **no Python imports** between `invoice_app/` and `client_app/`. They are separate copies of an early shared codebase.

## Desktop client (`client_app/`)

| Name | Meaning |
|------|---------|
| **FrogsWork** | User-facing product and brand (`APP_BRAND_NAME` in `app_config.py`) |
| **`client_app/`** | Repo folder: desktop client that talks to `billing_server/` over HTTP |
| **`FrogsWork.exe`** | PyInstaller build output |
| **`%APPDATA%\FrogsWork\`** | User data location |

Env vars: `FROGSWORK_BILLING_URL`, `FROGSWORK_DEV_BROWSER`, `FROGSWORK_ONEFILE` (build).

## Billing server (`billing_server/`)

| Name | Meaning |
|------|---------|
| **`billing_server/`** | Repo folder: Flask API |
| **`billing.db`** | SQLite database (runtime, gitignored) |
| **`billing_core.py`** | Fee math shared with client: keep in sync with `client_app/billing_core.py` |

Integration is **HTTP only** via `client_app/billing_client.py`.

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

Dev harness: `scripts/dev-test.ps1`.

Requirements: `requirements-client.txt` (FrogsWork), `requirements.txt` (Invoice App).

Build venv: `.client-venv/` (FrogsWork), `.build-venv/` (Invoice App).
