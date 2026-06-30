# FrogsWork, Commercial Product

Australian sole-trader desktop **sales invoicing** app (**FrogsWork**) with a free trial and Stripe subscription. Outgoing invoices only — not supplier bills or AP.

**Related docs:** **[DEPLOY](DEPLOY.md)** · [STRIPE_SETUP](STRIPE_SETUP.md) · [naming](naming.md) · [billing rules](billing-rules.md) · [security](security-risk-model.md) · [marketing site](../../marketing_site/README.md)

**Code:** [`client_app/`](../../client_app/) (desktop) · [`account_api/`](../../account_api/) (API: `dev/` + `worker/`)

---

## Quick start (local dev)

```powershell
# From repo root — opens API + app in two terminals
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `account_api/dev/.dev.vars.example` → `.dev.vars` and add Stripe keys + payment links. Run `.\scripts\configure-payment-links.ps1` once after setup.

Reset local state:

```powershell
.\scripts\reset-dev.ps1 -Force                  # clear AppData + API db
.\scripts\reset-dev.ps1 -Force -Seed -ResetSeed # fresh env + sample data
```

---

## Production deploy

**Start here:** [DEPLOY.md](DEPLOY.md) — Worker, R2 releases, marketing site.

Stripe Dashboard: [STRIPE_SETUP.md](STRIPE_SETUP.md).

---

## Build release

```powershell
.\client_app\build.ps1
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "Release note."
```

See [RELEASE.md](RELEASE.md).

---

## Pricing (summary)

- **Free trial:** 20 invoices or $20,000 ex GST (lifetime)
- **Subscribe:** $12.99/month or $129.90/year
- **Offline:** subscribed users get 14-day grace before verify required

Full rules: [billing-rules.md](billing-rules.md).

---

Made by [KorraOne.com](https://korraone.com)
