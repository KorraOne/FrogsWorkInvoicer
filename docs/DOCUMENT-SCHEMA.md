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
| `logo_*` | various | Logo paths (local only until cloud asset upload) |

### Customer (`customers.json` / `doc_customers`)

Keyed by customer name.

| Field | Type |
|-------|------|
| `email` | string |
| `phone` | string |
| Address fields | string |
| `due_rule_type`, `due_net_days` | optional overrides |

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
| `due_date`, `due_rule_type`, `due_net_days` | optional |
| `deleted_at` | ISO datetime if soft-deleted |

### Settings (`settings.json` / `doc_settings`)

| Field | Type |
|-------|------|
| `default_business` | string |
| `due_rule_type`, `due_net_days` | defaults |
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
- `upsert_settings` — `{ settings: { ... } }` (merged into existing)
- `enqueue_email_send` — `{ invoice_number }` (chains PDF generate → email)

## API routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/documents/bootstrap` | Full cache snapshot |
| POST | `/documents/migrate` | Local → cloud import |
| POST | `/documents/sync` | Apply mutation batch |
| GET | `/documents/invoices/{n}/pdf` | Download PDF (base64 JSON) |
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
