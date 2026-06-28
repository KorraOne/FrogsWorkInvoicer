# Invoice App: Product Description (Agent Context)

> **Repo context:** This document describes the **grandparents app** only (`invoice_app/`). The same repo also contains the commercial FrogsWork desktop app (`client_app/`) and billing server (`billing_server/`). See the [root README](../README.md) and [commercial docs](commercial/README.md).

## Overview

**Invoice App** (internal repo folder: `GrandparentsInvoicer/invoice_app/`) is a **Windows desktop invoicing tool** built for **personal/family business use**, specifically tailored for an Australian business creating **GST tax invoices**. It is designed for non-technical users (e.g. grandparents) with a large, accessible UI.

The app is **not a hosted web service**. It is a **local Flask web app** bundled with **PyInstaller** into `InvoiceApp.exe`, which:

1. Starts a local HTTP server on `http://127.0.0.1:5000`
2. Opens the default browser automatically
3. Shuts down after **90 seconds of idle time** or when the user clicks **Close App**

**Author/branding:** KorraOne.com (v1.0)

---

## Purpose & Domain

The product solves a narrow problem: **create professional Australian tax invoice PDFs, track whether they've been sent/paid, and manage a small customer list**: without accounting software complexity.

**Australian tax specifics:**

- All line-item amounts are entered **excluding GST**
- GST is computed at **10%** on the subtotal
- Totals shown as **TOTAL AUD (inc GST)**
- ABN formatting: `XX XXX XXX XXX` (11 digits)
- Bank account formatting: `XXX XXX` (6 digits)
- Invoice numbers: **8-digit zero-padded** (e.g. `00000056`)
- PDF filename pattern: `Invoice_{00000056}_{2026-06-26}.pdf`

**Default seeded business** (first-run defaults in `storage.py`):

- Marri Downs Holdings Pty Ltd
- PO Box 200, Boyanup WA 6237
- ABN 61164343300
- BSB 036-122, Account 549645
- Payment terms: "Net 30th after"
- Invoice counter starts at 56
- One default customer: Rodwell Farms

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  InvoiceApp.exe (PyInstaller, windowless console)       │
│  ┌───────────────────────────────────────────────────┐  │
│  │  app.py: Flask server @ 127.0.0.1:5000           │  │
│  │  • Jinja2 HTML templates + static CSS               │  │
│  │  • Routes for CRUD + invoice workflow               │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  pdf_generator.py: ReportLab A4 PDF generation   │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  storage.py: JSON persistence in %APPDATA%       │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  %APPDATA%\InvoiceApp\          Same folder as .exe\
  settings.json                  Generated PDF files
  customers.json
  invoices.json
  README.txt
```

### Tech stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3 |
| Web framework | Flask 3.x |
| PDF | ReportLab 4.x |
| Images | Pillow (dependency) |
| Packaging | PyInstaller 6.x |
| Frontend | Server-rendered Jinja2 HTML + vanilla JS |
| Persistence | JSON files on disk (no database) |

### Build & distribution

- Root `build.ps1` creates an isolated `.build-venv`, installs `requirements.txt`, runs PyInstaller
- Spec file: `invoice_app/InvoiceApp.spec`
- Default build: **onedir** → `invoice_app/dist/InvoiceApp/InvoiceApp.exe` (faster startup)
- Optional: **onefile** via `.\build.ps1 -OneFile` (env `INVOICEAPP_ONEFILE=1`)
- PyInstaller bundles `templates/` and `static/` as data files
- `resource_path()` resolves template/static paths for both dev and frozen exe
- `exe_dir()` = directory containing the running `.exe`: **PDFs are written here**, not in AppData

### Lifecycle / shutdown behavior

- `main()` starts threaded Werkzeug server, idle watchdog, and browser opener
- `@app.before_request` updates `last_request_time` (except `/shutdown`)
- Idle watchdog checks every 60s; shuts down after 90s idle
- Client-side `base.html` pings `POST /ping` every 30s to keep session alive while browsing
- `GET/POST /shutdown` triggers graceful server shutdown + `os._exit(0)`
- Done page has **Close App** button that calls `/shutdown` then `window.close()`

---

## Data Model

### Settings (`%APPDATA%\InvoiceApp\settings.json`)

```json
{
  "business_name": "...",
  "business_address": "multiline\nstring",
  "business_abn": "61164343300",
  "account_name": "...",
  "bsb": "036-122",
  "acc": "549645",
  "payment_terms": "Net 30th after",
  "invoice_counter": 57
}
```

- `invoice_counter` = **next** invoice number to assign (incremented after each PDF generation)
- `_migrate_settings()` backfills missing keys from defaults on load

### Customers (`customers.json`)

Dict keyed by **customer name** (name is the primary key; not editable after creation):

```json
{
  "Rodwell Farms": {
    "address": "PO Box 72\nBoyanup WA 6230",
    "abn": "65429514308"
  }
}
```

### Invoices (`invoices.json`)

Dict keyed by **8-digit padded invoice number string**:

```json
{
  "00000056": {
    "invoice_number": 56,
    "invoice_date": "2026-06-26",
    "customer_name": "Rodwell Farms",
    "description": "Lease – Lowrie Quarter (+2 more)",
    "total_inc_gst": "14850.00",
    "filename": "Invoice_00000056_2026-06-26.pdf",
    "status": "not_sent",
    "sent_date": null,
    "paid_date": null
  }
}
```

**Invoice status workflow** (strict one-way transitions only):

```
not_sent → sent → paid
```

- `update_invoice_status()` rejects invalid transitions
- Setting `sent` records `sent_date`; `paid` records `paid_date`
- Invoice list summary description: first line item description, or `"{first} (+N more)"` for multi-item

---

## User Flows & Screens

### 1. Home (`/`)

Navigation hub with large touch-friendly cards:

- Create Invoice
- Past Invoices
- Customers
- Settings

### 2. Create Invoice (`/create`): Step 1 of 2

- Shows next invoice number (read-only preview)
- Customer dropdown (from saved customers)
- **Dynamic line items** (JS: add/remove rows):
  - Description (text)
  - Qty (defaults to 1)
  - Unit price ex GST
- Optional comment/notes field
- Submit → `POST /preview`

### 3. Review Invoice (`/preview`): Step 2 of 2

- Read-only summary of all invoice fields
- Shows subtotal, GST 10%, total inc GST
- Bank payment details preview
- **Yes: Generate Invoice** → `POST /generate`
- **No: Go Back and Fix** → `POST /create` (preserves form via hidden fields)

### 4. Generate (`POST /generate`)

Side effects (atomic from user perspective):

1. Validates customer + line items
2. Calls `pdf_generator.generate_invoice(exe_dir(), invoice_data)`
3. Increments `invoice_counter` in settings
4. Adds record to `invoices.json` with status `not_sent`
5. Redirects to `/done?file=...&invoice=...&customer=...`

### 5. Done (`/done`)

Post-generation checklist UI:

1. View Invoice PDF (opens in new tab)
2. "I've sent this invoice" → marks as sent, stays on done page with success message
3. Create Another Invoice (pre-fills same customer), Go Home, Past Invoices, Close App

### 6. Past Invoices (`/invoices`)

Three collapsible `<details>` sections:

- **Not sent yet**: View PDF + "I've sent this invoice"
- **Sent: waiting for payment**: shows count + total owing; View PDF + "Mark as paid"
- **Paid**: View PDF only (read-only archive)

Sorted by date + number descending within each group.

### 7. Customers (`/customers`, `/customers/add`, `/customers/edit/<name>`, `/customers/delete/<name>`)

Full CRUD. Customer name is immutable after creation (disabled on edit form). Delete is POST-only.

### 8. Settings (`/settings`)

Edit business details, bank info, payment terms, and manually set next invoice number (must be ≥ 1).

---

## HTTP Routes Reference

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Home |
| GET/POST | `/create` | Invoice form (POST preserves form when going back from preview) |
| POST | `/preview` | Validate & show review |
| POST | `/generate` | Create PDF + persist invoice |
| GET | `/view-pdf/<filename>` | Serve PDF from exe directory (path traversal guarded) |
| GET | `/done` | Post-generation success page |
| POST | `/ping` | Keep-alive (204) |
| GET/POST | `/shutdown` | Stop server |
| GET | `/invoices` | Past invoices list |
| POST | `/invoices/<number>/status` | Transition status (`sent` or `paid`); optional `next=done` |
| GET | `/customers` | Customer list |
| GET/POST | `/customers/add` | Add customer |
| GET/POST | `/customers/edit/<name>` | Edit customer |
| POST | `/customers/delete/<name>` | Delete customer |
| GET/POST | `/settings` | Business settings |

**Jinja filters:** `fmt_invoice_number`, `fmt_invoice_date`, `fmt_invoice_amount`

---

## Core Business Logic (`app.py`)

### Amount parsing

- `parse_amount()`: strips `$` and commas, uses `Decimal`, rejects negative
- `parse_quantity()`: empty → 1; must be > 0
- `parse_line_items()`: zips parallel form lists, skips fully empty rows, validates each row, computes `line_total = qty × unit_amount_ex_gst`
- `compute_gst(subtotal)`: `gst = subtotal × 0.10` (quantized to 2dp), `total = subtotal + gst`

### Formatting helpers

- Money: `$4,500.00`
- Invoice number: `00000056`
- ABN/account: digit-grouped display (PDF and HTML preview)

---

## PDF Layout (`pdf_generator.py`)

A4 ReportLab document with:

- **Header:** business name/address/ABN (left) + "Tax Invoice" title, invoice #, date, terms (right)
- Accent divider bar (`#2c3e50`)
- **Bill To** section with customer name, address, ABN
- **Line items table:** Description | Qty | Unit (ex GST) | Amount (ex GST)
- **Totals:** Subtotal ex GST, GST 10%, TOTAL AUD
- **How to pay** box: account name, BSB, account, payment terms, reference = invoice #
- **Notes** section if comment provided

Styling: Helvetica, light grey table headers, bordered tables, professional but simple.

---

## UI/UX Design Notes

- **Accessibility-first:** large fonts (body 1.25rem, buttons 1.5rem), high contrast, 56px min button height
- **Segoe UI** font family
- Primary blue `#0056b3`, clean white background
- Card-based navigation on home
- Collapsible invoice sections with count badges
- Status badges: not_sent (amber), sent (blue), paid (green)
- Minimal JavaScript: line-item add/remove, keep-alive ping, close-app shutdown
- No authentication, no multi-user, no network exposure (localhost only)

---

## File Structure

This app lives in `invoice_app/` inside the monorepo. Sibling folders (not part of this app): `client_app/` (commercial FrogsWork), `billing_server/`. See [root README](../README.md).

```
invoice_app/
├── app.py                # Flask app, routes, main entry point
├── storage.py            # JSON persistence, defaults, invoice status
├── pdf_generator.py      # ReportLab PDF builder
├── InvoiceApp.spec       # PyInstaller configuration
├── templates/            # 9 HTML templates
├── static/style.css
├── build/                # PyInstaller intermediates (gitignored)
└── dist/                 # Build output (gitignored)
```

Repo root also has `build.ps1`, `requirements.txt`.

---

## Explicit Non-Goals / Limitations

The app does **not**:

- Send emails or integrate with payment gateways
- Support multiple currencies (AUD only)
- Store full line-item detail in `invoices.json` (only summary description + total)
- Allow editing or voiding invoices after generation
- Allow backward status transitions (e.g. sent → not_sent)
- Support credit notes, partial payments, or recurring invoices
- Run as a persistent background service (designed to open, do work, close)
- Work cross-platform out of the box (Windows-focused: `%APPDATA%`, `.ps1` build, `os._exit`)
- Provide user authentication or encryption
- Version-control or backup data automatically

---

## Development Notes for Agents

1. **Two storage locations matter:** AppData JSON for config/tracking; exe directory for PDF files. Don't conflate them.
2. **Invoice number in URLs/templates** uses formatted 8-digit string; storage uses integer in record + zero-padded key.
3. **Preview → Generate** passes data via hidden form fields (not server-side session state).
4. **GST is always 10%** hardcoded: not configurable.
5. **Customer is selected by exact dict key match**: the dropdown `value` must match `customers.json` key.
6. When running unfrozen (`python app.py`), PDFs land in `invoice_app/` directory; when frozen, next to the exe.
7. Werkzeug logging is suppressed to ERROR level for cleaner desktop experience.
8. `ensure_app_identity()` writes a human-readable `README.txt` in AppData on every startup explaining the data folder.

---

## Typical End-to-End Session

1. User double-clicks `InvoiceApp.exe`
2. Browser opens to Home
3. User goes to Create Invoice → selects customer → enters line items → Review
4. User confirms → PDF saved beside exe → invoice counter incremented → record added as `not_sent`
5. User views PDF, emails it manually, clicks "I've sent this invoice"
6. Later, after bank payment, user opens Past Invoices → Sent section → "Mark as paid"
7. User clicks Close App or walks away → app auto-shuts down after 90s idle
