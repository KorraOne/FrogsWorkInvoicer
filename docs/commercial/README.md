# FrogsWork, Commercial Product

Australian sole-trader desktop **sales invoicing** app (**FrogsWork**) with usage-based pricing. Outgoing invoices and accounts receivable only. Not supplier bills or AP.

**Related docs:** **[DEPLOY](DEPLOY.md)** · [naming](naming.md) · [terminology](terminology.md) · [brand](brand.md) · [release & install](RELEASE.md) · [marketing site](../../marketing_site/README.md) · [billing rules](billing-rules.md) · [security](security-risk-model.md) · [billing ledger guide](billing-ledger-guide.md) · [operator admin](operator-admin.md)

**Code:** [`client_app/`](../client_app/) (desktop) · [`billing_server/`](../billing_server/) (API)

The grandparents app in [`invoice_app/`](../invoice_app/) is a separate copy with no shared imports.

---

## Quick start

From repo root:

```powershell
.\scripts\dev-test.ps1 -Action StartAll          # billing server + desktop window
.\scripts\dev-test.ps1 -Action StartAll -DevBrowser
.\scripts\dev-test.ps1 -Action ResetAll -Force     # wipe AppData + billing.db
.\scripts\dev-test.ps1 -Action SeedDevData -Force  # dev customers/invoices/PDFs
```

Other actions: `StartServer`, `StartApp`, `TestOffline`, `TestOnline`, `ClearAppData`, `ClearDb`.

Edit seed data in [`client_app/seed_dev_data.py`](../client_app/seed_dev_data.py).

### Manual run

```powershell
# Desktop
cd client_app
pip install -r ..\requirements-client.txt
$env:BILLING_SERVER_URL = "http://127.0.0.1:8080"
python app.py

# Billing server
cd billing_server
pip install -r requirements.txt
$env:JWT_SECRET = "change-me"
python app.py
```

Use `$env:FROGSWORK_DEV_BROWSER = "1"` or `python app.py --dev-browser` for a normal browser instead of the embedded window.

---

## Production deploy

**Start here:** [DEPLOY.md](DEPLOY.md) — ordered checklist for `frogswork.com`, `api.frogswork.com`, Pi, and first release.

---

## Build & test exe

```powershell
.\build_client.ps1
# Production API URL (baked into exe):
.\build_client.ps1 -BillingUrl "https://api.frogswork.com"

# Full release (build + installer + zip + manifest):
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "Release note."
```

Outputs: `client_app\dist\FrogsWork\`, `FrogsWork-x.y.z-setup.exe`, `FrogsWork-x.y.z-win64.zip`, `marketing_site\releases.json`. Requires **Inno Setup 6** on the build PC. See [RELEASE.md](RELEASE.md).

```powershell
.\scripts\dev-test.ps1 -Action TestOffline -Force   # free tier, no server
.\scripts\dev-test.ps1 -Action TestOnline -Force    # account + server sync
```

**WebView2:** Required on Windows for the embedded window. [Runtime download](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) if needed.

### Platform billing job

```powershell
cd billing_server
python run_billing_job.py --quarter 1 --year 2026
```

Or use the admin UI at `/admin`. See [operator-admin.md](operator-admin.md).

---

## Data locations

| Data | Location |
|------|----------|
| Settings, customers, invoices, billing cache | `%APPDATA%\FrogsWork\` |
| Sales invoice PDFs | `%APPDATA%\FrogsWork\pdfs\` or custom folder |
| Billing DB (server) | `billing_server/billing.db` |

Billing URL resolution: stored auth URL → `BILLING_SERVER_URL` env → `FROGSWORK_BILLING_URL` → default in `app_config.py` (set at build via `-BillingUrl`).

---

## Pricing (summary)

- **$2,000/month free** sales invoiced ex-GST
- **0.05%** fee on ex-GST above free tier, per calendar month
- Optional user cap; platform fee invoice quarterly (+10% GST on fees)

Full rules: [billing-rules.md](billing-rules.md).

---

Made by [KorraOne.com](https://korraone.com)
