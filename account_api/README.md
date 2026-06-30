# FrogsWork account API

Auth, Stripe subscriptions, entitlements, and client release metadata for the desktop app.

| Subfolder | Runtime | Use |
|-----------|---------|-----|
| [`dev/`](dev/) | Flask (Python) | Local development on `http://127.0.0.1:8787` |
| [`worker/`](worker/) | Cloudflare Worker | Production `api.frogswork.com` |

Start both API and desktop app from repo root:

```powershell
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `dev/.dev.vars.example` → `dev/.dev.vars` and add Stripe test keys.

## Dev vs worker

The Flask dev server mirrors the Worker HTTP contract for local testing. Keep route behaviour in sync when changing either side.

## Docs

- [STRIPE_SETUP.md](../docs/commercial/STRIPE_SETUP.md)
- [DEPLOY.md](../docs/commercial/DEPLOY.md)
