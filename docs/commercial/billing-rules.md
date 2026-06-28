# Billing Rules (Locked)

## Usage month

- Free tier: **$2,000 ex-GST per calendar month**
- Fee: `monthly_fee = 0.0005 × (x − 2000)` when x > 2000
- Cap: optional max ex-GST per month; blocks generate until raise or explicit bypass

## Account required when

1. A single **sales invoice** exceeds $2,000 ex-GST, OR
2. Next **sales invoice** would push the calendar month over $2,000 ex-GST, OR
3. User enables a cap, OR
4. Voluntary signup

See [security-risk-model.md](security-risk-model.md) for offline ledger integrity and tamper protections.

## Offline

- Under free tier, cap off: **offline OK**
- Fee-bearing or cap enabled: **online required**

## Platform fee billing (separate from sales invoices)

- Usage fees accrue **per calendar month** (see above)
- **Platform fee invoice** from KorraOne: one PDF aggregating unbilled monthly fees for the billing period
- **Quarterly (default):** invoice after each calendar quarter (Jan–Mar, Apr–Jun, …). Up to 3 line items when all months had fees.
- **Annual (opt-in):** one invoice after each calendar year (Jan–Dec). Up to 12 line items.
- Each usage month appears on **at most one** platform invoice (tracked via line items; cycle changes only bill unbilled months)
- Subtotal + **10% GST**, paid manually via bank transfer / PayID
- Not related to sales invoices you send customers (accounts receivable)
