# FrogsWork, Commercial Product

Australian sole-trader desktop **sales invoicing** app (**FrogsWork**) with a free trial and Stripe subscription. Outgoing invoices only — not supplier bills or AP.

**Related docs:** **[DEPLOY](DEPLOY.md)** · [STRIPE_SETUP](STRIPE_SETUP.md) · [naming](naming.md) · [billing rules](billing-rules.md) · [security](security-risk-model.md) · [marketing site](../../marketing_site/README.md)

**Code:** [`client_app/`](../../client_app/) (desktop) · [`workers/frogswork-api/`](../../workers/frogswork-api/) (API) · [`frogswork_api/`](../../frogswork_api/) (local dev API)

---

## Quick start (local dev)

```powershell
# From repo root — opens API + app in two terminals
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `frogswork_api/.dev.vars.example` → `.dev.vars` and add Stripe keys + payment links.

Or run separately:

```powershell
.\scripts\start-dev-api.ps1
.\scripts\start-dev-app.ps1 -DevBrowser
```

---

## Production deploy

**Start here:** [DEPLOY.md](DEPLOY.md) — Worker, R2 releases, marketing site.

Stripe Dashboard: [STRIPE_SETUP.md](STRIPE_SETUP.md).

---

## Build release

```powershell
.\build_client.ps1
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
