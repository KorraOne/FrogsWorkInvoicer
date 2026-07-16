# Mobile UX (PWA v2)

Information architecture, flows, wireframes, and branding checklist for `client_web_v2`.

## Principles

1. One primary action per screen
2. Progressive disclosure (filters / advanced fields collapsed by default)
3. Sheets over navigation hops (inline customer, invoice actions, confirms)
4. Thumb-zone CTAs; destructive actions confirmed in sheets
5. No `alert()` / `confirm()` in primary flows — toasts and sheets
6. Empty states that explain the next step

## Information architecture

```
Welcome ──cloud──► Home
   │                  │
   └──local──► Upgrade
                      ├── Invoices → Create → Preview → Success sheet
                      ├── Customers → Add / Edit
                      └── Settings → Account | Business list | Payment terms | Help
```

### FAB

| Tab | FAB |
|-----|-----|
| Home | Hidden (hero Create button) |
| Invoices | `+` → Create |
| Customers | `+` → Add |
| Settings | Hidden |
| create / preview | Hidden |

## Wireframes

### Welcome

```
[FrogsWork logo]
Sales invoicing for Australian sole traders

┌ white card ─────────────────┐
│ message / error               │
│ Email    [________________] │
│ Password [________________] │
│ [       Sign in           ] │
│ Forgot password?              │
│ Create account →              │
└───────────────────────────────┘
KorraOne · frogswork.com
```

No web sign-in. No reset session.

### Upgrade

Same logo treatment (smaller). Title, signed-in email, Local vs Cloud bullets, primary Upgrade CTA, optional Manage subscription, Use a different account.

### Home

```
Sales this month  $X,XXX.XX
  ex GST $… (if GST)
Outstanding (N)   $X,XXX.XX
Paid all time     $X,XXX.XX
[ Create sales invoice ]
Past invoices →
```

### Invoices list

```
Past invoices                    [Create]
[ Filters ▾ ]  (n active)

▾ Not sent yet (2)
  card… [Send][PDF][···]
▾ Sent · $owing (3)
  due countdown… [Paid][PDF][···]
▸ Paid (12)
```

`···` sheet: Move to Not sent / Sent / Paid · Remove

### Create

```
← Cancel · Create invoice
From [biz] · # · Date
Customer [▾] [+ Add]   ← sheet
Line items…
Payment due [rules]
Notes · Work photos (≤6)
Totals · [ Preview ]
```

### Preview / Success

Scrollable paper preview → Save → success sheet: View PDF · Send · Done.

### Customers / Settings

Cards with email + suburb/state. Settings hub nav cards with hints. Multi-business list → full form (address, bank, GST, logo).

## Branding checklist ([`brand.md`](brand.md))

- [x] Tokens synced from desktop `theme.css` (`--fw-green-*`, page wash, surface, error)
- [x] Soft green radial wash; white cards for forms (not full splash green behind long forms)
- [x] One green primary CTA per screen; secondary = white + green border
- [x] Welcome / Upgrade: logo, tagline, KorraOne footer credit only
- [x] In-app: text title “FrogsWork”, no logo on Home
- [x] PDFs stay neutral black/white (brand greens are UI-only)
- [x] Body ~1.125rem+, tap targets ≥40–52px
- [x] Plain English labels; short hints under CTAs
- [x] PWA theme-color `#16a34a`; icons / apple-touch-icon aligned
