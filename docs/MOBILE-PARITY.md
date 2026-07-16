# Client parity (mobile PWA + browser + desktop shell)

One core UI: [`client_web_v2/`](../client_web_v2/). Hosts differ; the product does not.

| Host | How it runs |
|------|-------------|
| Mobile PWA | `app.frogswork.com` installed to home screen |
| Browser | Same origin in a normal tab |
| Windows desktop | pywebview shell loads the same Cloud UI |

## Decisions

| Topic | Choice |
|-------|--------|
| Multi-business | Full parity |
| Work photos | Include (≤6, camera/gallery, PDF appendix) |
| Manual send | Auto-send only |
| Scope | Cloud subscribers only |
| Welcome gate | In-app email/password |
| Host flag | `window.frogsworkDesktop` (shell): system browser links, hide PWA install chrome |
| Layout | Bottom nav on small screens; side nav + wider content from ~900px |
| Branding | [`brand.md`](brand.md) + desktop `theme.css` tokens |
| Free period | Stripe coupons / subscription trials only (no in-app trial meter) |

## Out of scope (this product cut)

- Local document API / Local SKU storefront (see decision gate in PLATFORM-ARCHITECTURE)
- Guest trial
- Backup ZIP / cloud migrate wizard in the Cloud UI
- Reveal PDF in Explorer / local file paths as primary flows
- macOS shell / Tauri rewrite

## Feature matrix (target)

### Auth and account

| Feature | Target |
|---------|--------|
| Email/password sign-in | In-app on Welcome |
| Subscription gate | Upgrade screen (Local-tier accounts until Local returns) |
| Account: email, status, portal | Settings → Account |
| Resend verification | Yes |
| Guest / local trial | N/A |

### Home / dashboard

| Feature | Target |
|---------|--------|
| Sales this month (inc + ex GST if registered) | Parity |
| Outstanding (total + count) | Parity |
| Paid (all time) | Parity |
| Create CTA + past invoices link | Yes |

### Customers / invoices / settings

See historical mobile notes in git history for screen-level justifications. Behaviour matches Cloud API documents + email send.

## Desktop shell notes

- Sessions are separate from browser PWA (WebView2 storage).
- Retest PDF iframe/download in WebView2 after shell changes.
- Packaging: single Cloud-oriented setup.exe + update zip ([installer README](../client_app/installer/README.md)).
