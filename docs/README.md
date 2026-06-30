# FrogsWork documentation

Operator docs for deploy, naming, and brand.

**Monorepo overview:** [../README.md](../README.md)

**Code:** [`client_app/`](../client_app/) · [`account_api/`](../account_api/) · [`client_app/ARCHITECTURE.md`](../client_app/ARCHITECTURE.md) · [`account_api/ROUTES.md`](../account_api/ROUTES.md)

---

## Doc index

| Doc | Contents |
|-----|----------|
| **[DEPLOY.md](DEPLOY.md)** | Production deploy — Worker, R2 releases, marketing site |
| [naming.md](naming.md) | Folder names, product vs exe/AppData, consistent wording |
| [brand.md](brand.md) | Visual identity and color tokens |

Component READMEs: [marketing site](../marketing_site/README.md) · [account API worker](../account_api/worker/README.md) · [installer](../client_app/installer/README.md)

---

## Quick start (local dev)

```powershell
# From repo root — API + app in two terminals
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `account_api/dev/.dev.vars.example` → `.dev.vars` and add Stripe test keys. Run `.\scripts\configure-payment-links.ps1` once after setup.

Reset local state:

```powershell
.\scripts\reset-dev.ps1 -Force                  # clear AppData + API db
.\scripts\reset-dev.ps1 -Force -Seed -ResetSeed # fresh env + sample data
```

---

## Production deploy

**Start here:** [DEPLOY.md](DEPLOY.md)

---

Made by [KorraOne.com](https://korraone.com)
