# PWA v2 audit (v1 baseline)

Historical audit of the deleted v1 `client_web/` implementation and cloud API usage before the [`client_web_v2/`](../client_web_v2/) rebuild.

## Feature matrix

| Feature | Docs claim | v1 actual | v2 target |
|---------|------------|-----------|-----------|
| Cloud-only access | Yes | Yes (upgrade gate for Local) | Yes |
| Guest trial | Was documented | Removed from UI; token cleanup only | No |
| In-app login | — | Added late; fragile on iOS PWA | Primary |
| Web login handoff | `?next=pwa` | Query + hash paths | Query only |
| Service worker | Offline PWA | `sw.js` exists, never registered | No |
| Dashboard totals | Yes | Yes | Yes |
| Customers CRUD | Yes | Yes | Yes |
| Invoice create | Yes | Yes (no edit after save) | Yes |
| Invoice list + filters | Yes | Yes | MVP: list + status |
| Auto Send (email) | Cloud paid | `enqueue_email_send` mutation | Same |
| Manual send | Guest | UI remains; unused for Cloud | No |
| PDF view | Yes | API `GET …/pdf` | `/mobile/v1/invoices/:n/pdf` |
| Settings / business | Yes | Yes | Yes |
| Payment terms | Yes | Yes | Yes |
| Migrate wizard | Desktop | Not in PWA | No |
| Offline queue | Yes | IDB queue; online-first | Same pattern |

## API call graph (v1)

| Endpoint | Client file | Purpose |
|----------|-------------|---------|
| `POST /auth/login` | `js/api.js`, `js/app.js` | Gate login |
| `POST /auth/refresh` | `js/api.js` | 401 retry |
| `GET /entitlements` | `js/api.js`, `js/app.js` | Cloud gate + account |
| `POST /auth/resend-verification` | `js/api.js`, `views/settings.js` | Email verify |
| `GET /documents/bootstrap` | `js/sync.js` | Full snapshot → IDB |
| `POST /documents/sync` | `js/sync.js` | Mutation queue |
| `GET /documents/invoices/:n/pdf` | `js/api.js`, `views/invoices.js` | View PDF |

**Defined but unused in v1:** `guestSession`, `generatePdf`, `sendInvoice`.

## Auth failure modes

| Mode | Cause | v2 mitigation |
|------|-------|---------------|
| Welcome loop after web sign-in | iOS installed PWA vs Safari separate storage | In-app login primary |
| Form reload, no error | Native form submit when JS module failed | Vite bundle + `type="button"` |
| `//js/` module URLs | Double-slash pathname | `<base href="/">` + built assets |
| Stale service worker | Old SW intercepting fetch | No SW in v2 |
| Local user on welcome | Upgrade used same screen as sign-in | Dedicated upgrade screen |

## Schema contract (v2 must support)

From [`DOCUMENT-SCHEMA.md`](DOCUMENT-SCHEMA.md):

**Entities:** businesses, customers, invoices (8-digit key), settings singleton.

**Mutations:** `upsert_business`, `upsert_customer`, `delete_customer`, `create_invoice`, `update_invoice_status`, `delete_invoice`, `upsert_settings`, `enqueue_email_send`.

## Keep / drop / defer

| Item | Action |
|------|--------|
| JWT auth + refresh | **Keep** (API) |
| D1 `doc_*` + R2 PDFs | **Keep** |
| Stripe entitlements | **Keep**; v2 uses `GET /mobile/v1/account` |
| `/documents/*` for desktop | **Keep** unchanged |
| `/mobile/v1/*` namespace | **Add** (PWA-first slice) |
| Guest workspaces | **Defer** worker cleanup |
| Local relay `/email/invoices/:n/send` | **Defer** (desktop) |
| v1 `client_web/` | **Deleted** after the v2 cutover; recoverable from Git history |
| Service worker | **Drop** in v2 |
| Hash auth callback | **Drop** as primary |
