# FrogsWork account API

Auth, Stripe subscriptions, entitlements, and client release metadata for the desktop app.

| Subfolder | Runtime | Use |
|-----------|---------|-----|
| [`dev/`](dev/) | Flask (Python) | Local development on `http://127.0.0.1:8787` |
| [`worker/`](worker/) | Cloudflare Worker | Production `api.frogswork.com` |

**HTTP contract:** [`ROUTES.md`](ROUTES.md) — keep `dev/server.py` and `worker/src/index.js` in sync.

Start API + desktop app from repo root:

```powershell
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `dev/.dev.vars.example` → `dev/.dev.vars` and add Stripe test keys.

## Docs

- [DEPLOY.md](../docs/DEPLOY.md)
