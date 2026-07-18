# FrogsWork documentation

Operator docs for deploy, naming, and brand.

**Monorepo overview:** [../README.md](../README.md)

**Code:** [`client_app/`](../client_app/) · [`account_api/`](../account_api/) · [`client_app/ARCHITECTURE.md`](../client_app/ARCHITECTURE.md) · [`account_api/ROUTES.md`](../account_api/ROUTES.md)

---

## Doc index

| Doc | Contents |
|-----|----------|
| **[PLATFORM-ARCHITECTURE.md](PLATFORM-ARCHITECTURE.md)** | Features, architecture, and coupling — marketing, API, desktop, PWA, R2 |
| **[DEPLOY.md](DEPLOY.md)** | Production deploy — Worker, R2 releases, marketing site |
| **[DOCUMENT-SCHEMA.md](DOCUMENT-SCHEMA.md)** | Shared entity and sync contract (local, cloud, PWA) |
| **[DB-SCHEMA.md](DB-SCHEMA.md)** | D1/SQLite tables, ERD, and tenant isolation |
| [naming.md](naming.md) | Folder names, product vs exe/AppData, consistent wording |
| [brand.md](brand.md) | Visual identity and color tokens |
| [MOBILE-PARITY.md](MOBILE-PARITY.md) | Client parity: PWA, browser, and desktop shell hosts |
| [MOBILE-UX.md](MOBILE-UX.md) | PWA v2 IA, wireframes, branding checklist |
| [MACOS-DESKTOP.md](MACOS-DESKTOP.md) | Deferred macOS packaging notes |

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
