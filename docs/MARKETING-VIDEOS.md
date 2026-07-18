# Marketing video guides

Shot list and recording notes for FrogsWork marketing and support videos on [frogswork.com/guides.html](https://frogswork.com/guides.html).

Videos play from R2 (`downloads.frogswork.com/videos/`) via [`marketing_site/videos.json`](../marketing_site/videos.json). Publish by uploading files and setting `"published": true`.

## Before you record

- **1080p MP4**, H.264, **silent** with short text overlays (no narration).
- Slow, deliberate taps / mouse movement.
- **Fictional data only.** Prefer the seeded marketing demo account. Do not show real customer names, real invoices, or family data on screen.
- **Device:** use `"device": "iphone"` for PWA screen recordings; `"device": "desktop"` for Windows install, Stripe checkout, and uninstall.
- **Subscribe clip:** use a promo on live Stripe or a test-mode build. Do not show real card numbers.
- Generate poster JPGs and upload to R2 `videos/posters/`.
- Keep tutorials under **~45 seconds**; main walkthrough **2 to 3 minutes**.

## Main walkthrough

**File:** `walkthrough.mp4` · **Device:** iPhone PWA  
**Title on site:** See FrogsWork in under 3 minutes

1. Home dashboard: Sales this month, Outstanding, Paid all time.
2. Create invoice: customer, line items, payment due.
3. Save → success screen with embedded tax invoice PDF.
4. Send to customer by email.
5. Past invoices: search / filter, View PDF.
6. Mark paid → Home totals update.

## Short tutorials

| ID | Device | Category | Steps (summary) |
|----|--------|----------|-----------------|
| `install` | Windows | Install | frogswork.com Download → setup → Sign in → Home |
| `install-iphone` | iPhone | Install | Safari → Add to Home Screen |
| `install-android` | Android | Install | Chrome → Install app / Add to Home screen |
| `setup-business` | iPhone | Getting started | Settings → Business details → logo → Save |
| `setup-customer` | iPhone | Getting started | Customers → + → Save |
| `add-customer-inline` | iPhone | Invoicing | New invoice → + Add customer → selected |
| `creating-invoice` | iPhone | Invoicing | Lines → Save invoice → PDF success → Done |
| `managing-gst` | iPhone | Invoicing | GST registered → line GST toggle → PDF |
| `managing-past-invoices` | iPhone | Invoicing | Filter Not sent/Sent/Paid → View PDF / Mark paid |
| `send-invoice` | iPhone | Invoicing | Send / Send to customer → Sent status |
| `dashboard` | iPhone | Dashboard | Home totals → Create / Past invoices |
| `subscribing` | Windows | Subscription | Signup → Stripe → Settings → Account → Manage subscription |
| `uninstall` | Windows | Windows | Start menu uninstall; Cloud data still on app.frogswork.com |

Removed (Local-era): `backup-restore`, `pdf-location`.

Device hint on cards is muted copy: **Tutorial recorded on iPhone / Android / Windows**.

## Publish checklist

1. Upload MP4 to `videos/<file>.mp4` with `Content-Type: video/mp4`.
2. Upload poster to `videos/posters/<name>.jpg`.
3. Set `"published": true` in `videos.json` for that entry.
4. `cd marketing_site && npx wrangler deploy`.
5. Open `/guides.html` and confirm playback and poster.

## Homepage screenshot

After recording the walkthrough, save a dashboard frame as `marketing_site/assets/brand/hero-dashboard.png` for the homepage hero (desktop only; links to Video guides).

## Copy for overlays

Use plain Australian English. Match UI labels: **Business details**, **Save invoice**, **Send to customer**, **Mark paid**, **Not sent** / **Sent** / **Paid**. No em dashes in on-screen text.
