# Archived: Pi usage billing server

**Retired.** FrogsWork now uses Stripe subscriptions via [`workers/frogswork-api/`](../../workers/frogswork-api/) (production) and trial gating in the desktop client.

This folder is the old Flask API for usage-based platform fees, monthly caps, and Pi autobilling. Do not deploy for new installs.

See [docs/commercial/billing-rules.md](../../docs/commercial/billing-rules.md) and [docs/commercial/DEPLOY.md](../../docs/commercial/DEPLOY.md).

---

## Historical reference (pre-subscription model)

Flask API for FrogsWork accounts, usage, and operator admin.

| Environment | URL |
|-------------|-----|
| **Was production** | `https://api.frogswork.com` (now the Cloudflare Worker) |
| **Local dev (old)** | `http://127.0.0.1:8080` |

Original Pi deploy docs remain in `deploy/` for reference only.
