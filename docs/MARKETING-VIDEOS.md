# Marketing video guides

Shot list and recording notes for FrogsWork marketing and support videos on [frogswork.com/guides.html](https://frogswork.com/guides.html).

Videos play from R2 (`downloads.frogswork.com/videos/`) via [`marketing_site/videos.json`](../marketing_site/videos.json). Publish by uploading files and setting `"published": true`.

## Before you record

- **1080p MP4**, H.264, silent with short text overlays (no narration required).
- Slow, deliberate mouse movement.
- **Fictional data only.** Run `python seed_marketing_demo.py --reset` from `client_app/`. Do not show real customer names, real invoices, or family data on screen.
- **Subscribe clip:** use EARLY100 on live Stripe or a test-mode build. Do not show real card numbers.
- Generate poster JPGs and upload to R2 `videos/posters/`.
- Keep tutorials under **40 seconds**; main walkthrough **2 to 3 minutes**.

## Main walkthrough

**File:** `walkthrough.mp4`  
**Title on site:** See FrogsWork in under 3 minutes

1. Open the app on the main dashboard. Business details set, customers populated, past invoices visible.
2. Create an invoice: select customer, add line items, toggle GST, add customer inline if needed.
3. Preview the invoice PDF. Show logo, totals, GST, due date.
4. Mark the invoice sent. Show status change and Outstanding list.
5. Open past invoices. Search and filter.
6. Mark an invoice paid. Dashboard updates.
7. Dashboard overview: totals, overdue count, paid vs outstanding.

## Short tutorials

| ID | File | Steps (summary) |
|----|------|-----------------|
| `install` | `install.mp4` | Website download → run installer → setup wizard |
| `setup-business` | `setup-business.mp4` | Business details, ABN, address, logo, save |
| `setup-customer` | `setup-customer.mp4` | Customers → add → save |
| `add-customer-inline` | `add-customer-inline.mp4` | New invoice → add customer inline |
| `creating-invoice` | `creating-invoice.mp4` | Customer, lines, due date, GST, save, PDF |
| `managing-gst` | `managing-gst.mp4` | GST in business details, line toggles, PDF |
| `managing-past-invoices` | `managing-past-invoices.mp4` | List, search, filter, change status |
| `dashboard` | `dashboard.mp4` | Totals, overdue, paid vs outstanding |
| `subscribing` | `subscribing.mp4` | Subscribe, Stripe checkout, manage billing |
| `backup-restore` | `backup-restore.mp4` | Backup file, restore, confirm data |
| `pdf-location` | `pdf-location.mp4` | Data storage → change PDF folder |
| `uninstall` | `uninstall.mp4` | Start menu uninstall, PDF export folder |

## Publish checklist

1. Upload MP4 to `videos/<file>.mp4` with `Content-Type: video/mp4`.
2. Upload poster to `videos/posters/<name>.jpg`.
3. Set `"published": true` in `videos.json` for that entry.
4. `cd marketing_site && npx wrangler deploy`.
5. Open `/guides.html` and confirm playback and poster.

## Homepage screenshot

After recording the walkthrough, save a dashboard frame as `marketing_site/assets/brand/hero-dashboard.png` for the homepage hero (desktop only; links to Video guides).

## Copy for overlays

Use plain Australian English. Match the marketing site voice: short labels, real UI names (**Business details**, **Prepare to send**, **Mark paid**). No em dashes in on-screen text.
