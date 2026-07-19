# FrogsWork document schema

Shared entity contract for **desktop local**, **desktop cloud**, **mobile PWA**, and the **document API**.

## Entities

### Business profile (`businesses.json` / `doc_businesses`)

Keyed by business name (string).

| Field | Type | Notes |
|-------|------|-------|
| `business_name` | string | Display name |
| `address_line1` … `postcode` | string | Structured AU address |
| `business_abn` | string | 11 digits |
| `gst_registered` | boolean | |
| `account_name`, `bsb`, `acc` | string | Bank details |
| `invoice_counter` | integer | Per-business numbering |
| `quote_counter` | integer | Per-business quote numbering (when Quotes enabled) |
| `logo_*` | various | Logo paths (local only until cloud asset upload) |

### Customer (`customers.json` / `doc_customers`)

Keyed by customer name.

| Field | Type |
|-------|------|
| `email` | string |
| `phone` | string |
| Address fields | string |
| `due_rule_type`, `due_net_days` | optional overrides |
| `created_via` | optional `inline` \| `list` (analytics origin) |

### Invoice (`invoices.json` / `doc_invoices`)

Keyed by `invoice_key` = zero-padded 8-digit number.

| Field | Type |
|-------|------|
| `invoice_number` | integer |
| `invoice_date` | ISO date |
| `customer_name` | string |
| `business_name` | string |
| `description` | string |
| `total_inc_gst`, `amount_ex_gst`, `gst_amount` | decimal strings |
| `filename` | string | PDF filename when ready |
| `pdf_status` | `pending` \| `ready` (cloud) |
| `status` | `not_sent` \| `send_queued` \| `send_failed` \| `sent` \| `paid` |
| `sent_date` | ISO date | set when sent |
| `paid_date` | ISO date | set when status becomes `paid` (cleared if moved back) |
| `due_date`, `due_rule_type`, `due_net_days` | optional |
| `deleted_at` | ISO datetime if soft-deleted |
| `source_quote_id`, `source_quote_number` | optional | set when created from a quote |

### Quote / price estimate (`doc_quotes`)

Keyed by `quote_key` (stable UUID / storage key). Optional feature via settings `quotes_enabled`.

| Field | Type | Notes |
|-------|------|-------|
| `quote_number` | integer | |
| `doc_kind` | `quote` \| `estimate` | PDF/email label |
| `quote_date` | ISO date | |
| `customer_name`, `business_name` | string | |
| Line items / GST totals | same shape as invoices | |
| `status` | `not_sent` \| `send_queued` \| `send_failed` \| `sent` \| `closed` \| `converted` | |
| `sent_date` | ISO datetime | set on successful send |
| `converted_invoice_id` | string | when converted to an invoice |
| `converted_invoice_number` | integer | denormalized for list display / filter links |
| `pdf_status` | `pending` \| `ready` | |
| `deleted_at` | ISO datetime if soft-deleted | |

Converted invoices also store `source_quote_id` and `source_quote_number` on the invoice JSON.

No due-date / how-to-pay fields on the PDF or email.

### Settings (`settings.json` / `doc_settings`)

| Field | Type |
|-------|------|
| `default_business` | string |
| `due_rule_type`, `due_net_days` | defaults |
| `quotes_enabled` | boolean | off by default; shows Quotes tab |
| `payment_followups_enabled` | boolean | off by default; auto payment reminder emails |
| `payment_followup_offset_days` | number | −14…14; default −3 (days relative to due date) |
| `storage_mode` | `local` \| `cloud` (desktop only) |
| `welcome_complete` | boolean |

## Sync queue mutations

FIFO replay via `POST /documents/sync`:

- `upsert_business` — `{ businesses: { ... } }`
- `upsert_customer` — `{ customers: { ... } }`
- `delete_customer` — `{ name }`
- `create_invoice` — `{ invoice }`
- `update_invoice_status` — `{ invoice_number, status }`
- `delete_invoice` — `{ invoice_number }` (soft delete via `deleted_at`)
- `create_quote` — `{ quote, prepare_pdf? }`
- `update_quote_status` — `{ quote_id, status, … }`
- `delete_quote` — soft delete
- `enqueue_quote_email` — queue quote PDF email
- `convert_quote_to_invoice` — `{ quote_id, invoice, prepare_pdf? }`
- `upsert_settings` — `{ settings: { ... } }` (merged into existing)
- `enqueue_email_send` — `{ invoice_number }` (chains PDF generate → email)
- `enqueue_followup_email` — `{ invoice_id }` payment reminder (does not change invoice status)

## API routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/documents/bootstrap` | Full cache snapshot (includes `quotes`) |
| POST | `/documents/migrate` | Local → cloud import |
| POST | `/documents/sync` | Apply mutation batch |
| GET | `/documents/invoices/{n}/pdf` | Download invoice PDF (base64 JSON) |
| GET | `/documents/quotes/{id}/pdf` | Download quote PDF (base64 JSON) |
| POST | `/documents/invoices/{n}/generate` | Server PDF generation |
| POST | `/documents/invoices/{n}/send` | Queue integrated email |
| POST | `/guest/session` | Guest cloud trial token |

## Entitlements extension

`GET /entitlements` includes:

```json
{
  "active": true,
  "storage_tier": "local",
  "platforms": { "desktop": true, "mobile": false }
}
```

Cloud tier sets `platforms.mobile: true`.

## Revisions

Cloud tables store `revision` and `updated_at` per row for optimistic concurrency (LWW v1).
