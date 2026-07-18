# Local product metrics dashboard

Fetches privacy-friendly aggregates from `GET /metrics/summary` using a Bearer token.
Run only on your machine — do not publish the dashboard or commit `.env`.

## Setup

1. Set Worker secret (production):

```bash
cd account_api/worker
npx wrangler secret put METRICS_TOKEN
```

2. Apply D1 migration once:

```bash
npx wrangler d1 execute frogswork-account --remote --file=../migrations/010_analytics_rebuild.sql
npx wrangler d1 execute frogswork-account --remote --file=../migrations/011_user_subscription_lifecycle.sql
```

3. Copy env locally:

```bash
cd tools/local_metrics
copy .env.example .env
# Edit METRICS_TOKEN and API_BASE
```

4. Fetch + open:

```powershell
.\fetch_summary.ps1
# Opens dashboard.html with the latest JSON embedded / printed
```

## GA4

Marketing: set `window.FW_GA4_MARKETING_ID` in `marketing_site/js/analytics-config.js`.  
Cloud: set `VITE_GA4_MEASUREMENT_ID` in `client_web_v2/.env.local` before build.
