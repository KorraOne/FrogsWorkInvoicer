# Mobile Cloud parity

Locked product decisions and per-screen element justifications for `client_web_v2`.

## Decisions

| Topic | Choice |
|-------|--------|
| Multi-business | Full parity |
| Work photos | Include (≤6, camera/gallery, PDF appendix) |
| Manual send | Auto-send only |
| Scope | Cloud subscribers only |
| Welcome gate | In-app login only — no “Sign in on web”, no “Reset session” |
| Branding | [`brand.md`](brand.md) + desktop `theme.css` tokens |
| Build order | Features first, UI/UX polish last |

## Out of scope

- Local storage mode, guest trial, trial meter
- Backup ZIP, cloud migrate wizard, app updater
- Manual email compose / copy-to-clipboard send
- Reveal PDF in Explorer / local file paths
- Desktop external-browser login as primary

## Feature matrix (target)

### Auth and account

| Feature | Target |
|---------|--------|
| Email/password sign-in | In-app only on Welcome |
| Subscription gate | Upgrade screen |
| Account: email, status, portal | Settings → Account |
| Resend verification | Yes |
| Guest / local trial | N/A |

### Home / dashboard

| Feature | Target |
|---------|--------|
| Sales this month (inc + ex GST if registered) | Parity |
| Outstanding (total + count) | Parity |
| Paid (all time) | Parity |
| Create CTA + past invoices link | Mobile-adapt |
| Account panel on Home | Removed (use Settings) |

### Customers

| Feature | Target |
|---------|--------|
| List with email + suburb/state | Parity |
| Add / edit / delete (in-use guard) | Parity |
| Inline add from invoice create | Mobile-adapt (sheet) |

### Invoices — list

| Feature | Target |
|---------|--------|
| Groups: Not sent / Sent (owing) / Paid | Parity |
| Filters: search, status, customer, business, dates | Parity |
| Due countdown on sent | Parity |
| Send / Mark paid / View PDF | Parity |
| Move status + Remove via `···` sheet | Parity |

### Invoices — create / send

| Feature | Target |
|---------|--------|
| Business picker, #, date, customer, lines, GST-free | Parity |
| Payment due rules, notes, work photos ≤6 | Parity |
| Rich save → embedded PDF success (Edit / Download / Send / Done) | Mobile-adapt |
| Auto send only | Parity |

### Business / settings

| Feature | Target |
|---------|--------|
| Multi-business CRUD | Parity |
| AU address, ABN, bank, GST, logo upload | Parity / mobile-adapt |
| Payment terms default, Help link, Sync | Parity |

## Element justification

Every control must earn its place. **Parity** = desktop/v1 cloud behavior. **Mobile-adapt** = same outcome, better mobile pattern. **Brand** = identity from `brand.md`. **Remove** = drop from target.

### Global chrome

| Element | Verdict | Why |
|---------|---------|-----|
| Sticky header “FrogsWork” | Keep | Wayfinding; Home does not show logo |
| Sync status in header | Keep | Queue flush feedback |
| Bottom nav | Keep | Parity IA |
| FAB on Invoices + Customers | Keep | Mobile-adapt primary create |
| FAB hidden Home / Settings / create / success | Keep | One primary action per screen |
| `theme-color` #16a34a | Keep | Brand |

### Welcome

| Element | Verdict | Why |
|---------|---------|-----|
| Logo + tagline | Add | Brand front door |
| White card on green wash | Add | Brand layout rule |
| Message / email / password / Sign in | Keep | Parity + iOS PWA-safe login |
| Forgot password / Create account | Keep | Parity / acquisition |
| Sign in on web / Reset session | Remove | User decision |
| Localhost API hint | Keep (dev only) | Operator convenience |

### Upgrade

| Element | Verdict | Why |
|---------|---------|-----|
| Logo + tagline | Add | Brand gate family |
| Title, signed-in email, lead, Local/Cloud list | Keep | Conversion context |
| Upgrade / Subscribe / Manage portal | Keep | Parity |
| Use a different account | Keep | Gate sign-out |

### Home

| Element | Verdict | Why |
|---------|---------|-----|
| Month / Outstanding / Paid totals | Keep / Add | Parity |
| ex GST when GST registered | Add | Parity |
| Create CTA + Past invoices link | Keep | Mobile-adapt |
| Account panel | Remove | Duplicates Settings |

### Invoices list

| Element | Verdict | Why |
|---------|---------|-----|
| Past invoices + Create | Keep | Parity |
| Filters + 3 groups + due countdown | Add | Parity |
| Send / Paid / PDF on card | Keep | Parity |
| `···` Move / Remove | Add | Parity; safer than inline Remove |
| Empty state | Add | Next-step clarity |

### Invoices create / success

| Element | Verdict | Why |
|---------|---------|-----|
| Cancel, biz, #, date, customer + Add, lines, totals | Keep | Parity |
| Due rules, notes, work photos | Add | Parity |
| Save → embedded PDF success | Add | Mobile-adapt; real PDF not HTML mock |
| Success: Edit / Download / Send / Done | Add | Mobile-adapt |

### Customers

| Element | Verdict | Why |
|---------|---------|-----|
| List + Add, form fields, delete guard | Keep | Parity |
| Address snippet on card | Extend | Parity |
| Inline sheet from invoice | Add | Mobile-adapt |

### Settings

| Element | Verdict | Why |
|---------|---------|-----|
| Nav cards with hints | Extend | Parity + brand voice |
| Account / Business / Payment terms / Sync / Help | Keep / Add | Parity |
| Sign out | Keep | Replaces Welcome reset |
| Multi-biz form (address, bank, GST, logo) | Add | Parity / mobile-adapt |

## API notes

- Invoice JSON may include `comment`, `due_*`, `work_photos_b64[]`.
- Business JSON may include `logo_b64` (fit-width preset; no drag editor on mobile v1).
- PDF worker embeds notes, work photos, and logo when present.
