# Operator admin guide

Web UI for checking FrogsWork uptake, usage, and platform fee invoices. Runs on the billing server at `/admin`.

**Related:** [DEPLOY.md](DEPLOY.md) · [billing rules](billing-rules.md) · [billing server README](../../billing_server/README.md)

---

## Access (production)

The admin UI is **not** on a public URL. The billing API binds to `127.0.0.1`; only Cloudflare Tunnel exposes `api.frogswork.com` for desktop clients.

From your laptop (SSH as **`pi`**, not `frogswork` — that user has no login password):

```bash
ssh -L 8008:127.0.0.1:8008 pi@<pi-hostname-or-tailscale-ip>
```

Open http://127.0.0.1:8008/admin and log in with `ADMIN_PASSWORD` from `/etc/frogswork/billing.env`.

Sessions expire after `ADMIN_SESSION_HOURS` (default 8).

**Local dev:** http://127.0.0.1:8080/admin with `.env` `ADMIN_PASSWORD`.

---

## Environment variables (Pi)

Set in `/etc/frogswork/billing.env` (see [`billing_server/deploy/production.env.example`](../../billing_server/deploy/production.env.example)):

| Variable | Required | Notes |
|----------|----------|-------|
| `HOST` | Yes | **`127.0.0.1`** in production |
| `PORT` | Yes | **`8008`** on Pi (avoid 8080 if other services use it) |
| `BASE_URL` | Yes | `https://api.frogswork.com` |
| `ADMIN_PASSWORD` | Yes | Strong operator password |
| `JWT_SECRET` | Yes | API token signing |
| `KORRAONE_*` | Before real invoices | Letterhead on platform PDFs |
| `CLIENT_RELEASE_*` | After first exe ship | In-app update metadata |

Platform PDF output: `PLATFORM_INVOICE_DIR` (default under `billing_server/`).

---

## Billing model (admin view)

- **Usage** is always tracked per calendar month.
- **Platform invoices** aggregate **unbilled** months only. Each month appears on at most one platform invoice (stored in line items).
- **Quarterly accounts (default):** generate after each calendar quarter (Q1–Q4).
- **Annual accounts:** generate once per calendar year (Jan–Dec), mode **Annual accounts** on Generate.

### Cycle changes

If a user switches quarterly ↔ annual mid-year, you do **not** need a separate per-month database table. The system derives billed months from past platform invoice line items.

- Only **unbilled** months in the selected period are included on the next invoice.
- Unbilled months from an **earlier** quarter/year show on the account as unbilled. Run Generate for that period to catch up (e.g. Q1 after switching from annual in May).

### Payment due dates

Accounts list and account detail show:

- **Payment due:** from `KORRAONE_PAYMENT_TERMS` (default 14 days after invoice date)
- **Accruing:** current period not finished yet
- **Ready to bill:** closed months with unbilled fees, or period ended
- **Awaiting payment:** platform invoice sent, not marked paid

---

## Admin pages

| Page | Purpose |
|------|---------|
| **Dashboard** | Account count, signups, usage/fees, unpaid totals, accounts needing action |
| **Accounts** | Billing status, payment due, unbilled fee total |
| **Account detail** | Per-month platform billing state (accruing / unbilled / invoiced / paid) |
| **Usage** | All accounts for a selected calendar month |
| **Platform invoices** | Generated bills; download PDF; mark paid |
| **Generate** | Quarterly or annual mode; preview unbilled months; generate PDFs |

---

## Typical workflow

### During the month

1. Open **Dashboard** or **Accounts**. Check status and unbilled totals.
2. **Accruing** is normal for the current quarter/year.

### End of quarter (quarterly accounts)

1. **Generate** → mode **Quarterly accounts** → pick year + quarter → **Preview**.
2. Confirm unbilled months listed per account.
3. **Generate invoices** → download from **Platform invoices** → send manually.
4. **Mark paid** when transfer arrives.

### End of year (annual accounts)

1. **Generate** → mode **Annual accounts** → pick year → same steps as above.

### CLI

```bash
cd billing_server
python run_billing_job.py --quarter 2 --year 2026
python run_billing_job.py --mode annual --year 2025
```

---

## Platform invoice PDFs

KorraOne → FrogsWork user bills (separate from sales invoices). Invoice numbers: `PF-2026-Q2-00001` (quarterly) or `PF-2026-Y-00001` (annual).

Populate `KORRAONE_*` in env before sending real invoices.

## User app (Settings → Billing)

Signed-in users see next payment due, billing cycle, monthly fee history, and platform invoice status via `GET /account/billing`. Changing cycle via `PATCH /account/billing-cycle` triggers quarterly backlog billing when switching from annual.
