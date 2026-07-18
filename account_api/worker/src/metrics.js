/**
 * Privacy-friendly aggregate product metrics for local dashboard use.
 * Returns counts, averages, histograms — never PII or document bodies.
 */

export function checkMetricsAuth(request, metricsToken) {
  if (!metricsToken) {
    return {
      ok: false,
      response: new Response(JSON.stringify({ error: "Metrics not configured." }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    };
  }
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  const token = match ? match[1].trim() : "";
  if (token !== metricsToken) {
    return {
      ok: false,
      response: new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    };
  }
  return { ok: true };
}

async function scalar(db, sql, ...binds) {
  const row = await db
    .prepare(sql)
    .bind(...binds)
    .first();
  if (!row) return 0;
  const key = Object.keys(row)[0];
  return Number(row[key]) || 0;
}

async function rows(db, sql, ...binds) {
  const result = await db
    .prepare(sql)
    .bind(...binds)
    .all();
  return result.results || [];
}

function pct(part, whole) {
  if (!whole) return null;
  return Math.round((1000 * part) / whole) / 10;
}

function avg(sum, count) {
  if (!count) return null;
  return Math.round((100 * sum) / count) / 100;
}

export async function buildMetricsSummary(db) {
  const accountsTotal = await scalar(db, "SELECT COUNT(*) AS c FROM users");
  const accountsActive = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE account_status = 'active' AND stripe_customer_id IS NOT NULL"
  );
  const accountsPending = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE account_status = 'pending_payment'"
  );
  const tierLocal = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE account_status = 'active' AND storage_tier = 'local'"
  );
  const tierCloud = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE account_status = 'active' AND storage_tier = 'cloud'"
  );

  const subscribed = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE subscribed_at IS NOT NULL"
  );
  const cancelScheduled = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE cancel_scheduled_at IS NOT NULL AND unsubscribed_at IS NULL"
  );
  const unsubscribed = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM users WHERE unsubscribed_at IS NOT NULL"
  );

  const tenureRows = await rows(
    db,
    `SELECT CAST((julianday(COALESCE(unsubscribed_at, datetime('now'))) - julianday(subscribed_at)) AS REAL) AS days
     FROM users
     WHERE subscribed_at IS NOT NULL`
  );
  const tenureDays = tenureRows
    .map((r) => Number(r.days))
    .filter((d) => Number.isFinite(d) && d >= 0)
    .sort((a, b) => a - b);
  const medianTenure =
    tenureDays.length === 0
      ? null
      : tenureDays.length % 2 === 1
        ? Math.round(tenureDays[(tenureDays.length - 1) / 2] * 10) / 10
        : Math.round(
            ((tenureDays[tenureDays.length / 2 - 1] + tenureDays[tenureDays.length / 2]) / 2) *
              10
          ) / 10;

  const invoicePerUser = await rows(
    db,
    `SELECT user_id, COUNT(*) AS n FROM doc_invoices GROUP BY user_id`
  );
  const invCounts = invoicePerUser.map((r) => Number(r.n) || 0);
  const invSum = invCounts.reduce((a, b) => a + b, 0);
  const cloudUsersWithDocs = await scalar(
    db,
    `SELECT COUNT(DISTINCT user_id) AS c FROM (
       SELECT user_id FROM doc_invoices
       UNION SELECT user_id FROM doc_customers
       UNION SELECT user_id FROM doc_businesses
       UNION SELECT user_id FROM doc_settings
     )`
  );
  const invBuckets = { "0": 0, "1-5": 0, "6-20": 0, "21+": 0 };
  const usersWithInvoiceRows = new Set(invoicePerUser.map((r) => r.user_id));
  // Bucket only accounts that have cloud doc activity; zeros = cloud users with no invoices
  const zeroInvoiceCloud = Math.max(0, cloudUsersWithDocs - usersWithInvoiceRows.size);
  invBuckets["0"] = zeroInvoiceCloud;
  for (const n of invCounts) {
    if (n <= 5) invBuckets["1-5"] += 1;
    else if (n <= 20) invBuckets["6-20"] += 1;
    else invBuckets["21+"] += 1;
  }

  const sentInvoices = await scalar(
    db,
    `SELECT COUNT(*) AS c FROM doc_invoices
     WHERE json_extract(data_json, '$.status') IN ('sent', 'paid', 'send_queued')
        OR json_extract(data_json, '$.status') LIKE '%sent%'`
  );
  const accountsWithSent = await scalar(
    db,
    `SELECT COUNT(DISTINCT user_id) AS c FROM doc_invoices
     WHERE COALESCE(json_extract(data_json, '$.status'), '') IN ('sent', 'paid', 'send_queued', 'send_failed')
        OR COALESCE(json_extract(data_json, '$.status'), '') = 'sent'
        OR COALESCE(json_extract(data_json, '$.status'), '') = 'paid'`
  );

  const dueTypeRows = await rows(
    db,
    `SELECT COALESCE(json_extract(data_json, '$.due_rule_type'), 'unknown') AS t, COUNT(*) AS c
     FROM doc_invoices
     GROUP BY t`
  );
  const dueTypes = Object.fromEntries(dueTypeRows.map((r) => [String(r.t), Number(r.c) || 0]));

  const settingsDueRows = await rows(
    db,
    `SELECT COALESCE(json_extract(data_json, '$.due_rule_type'), 'unknown') AS t, COUNT(*) AS c
     FROM doc_settings
     GROUP BY t`
  );
  const settingsDueDefaults = Object.fromEntries(
    settingsDueRows.map((r) => [String(r.t), Number(r.c) || 0])
  );

  const customerPerUser = await rows(
    db,
    `SELECT user_id, COUNT(*) AS n FROM doc_customers GROUP BY user_id`
  );
  const custCounts = customerPerUser.map((r) => Number(r.n) || 0);
  const custSum = custCounts.reduce((a, b) => a + b, 0);
  const custBuckets = { "0": 0, "1": 0, "2-5": 0, "6+": 0 };
  custBuckets["0"] = Math.max(0, cloudUsersWithDocs - customerPerUser.length);
  for (const n of custCounts) {
    if (n === 1) custBuckets["1"] += 1;
    else if (n <= 5) custBuckets["2-5"] += 1;
    else custBuckets["6+"] += 1;
  }

  const inlineCustomers = await scalar(
    db,
    `SELECT COUNT(*) AS c FROM doc_customers
     WHERE json_extract(data_json, '$.created_via') = 'inline'`
  );
  const listCustomers = await scalar(
    db,
    `SELECT COUNT(*) AS c FROM doc_customers
     WHERE json_extract(data_json, '$.created_via') = 'list'
        OR json_extract(data_json, '$.created_via') IS NULL`
  );
  const customersTotal = inlineCustomers + listCustomers;

  const bizPerUser = await rows(
    db,
    `SELECT user_id, COUNT(*) AS n FROM doc_businesses GROUP BY user_id`
  );
  const multiBiz = bizPerUser.filter((r) => Number(r.n) > 1).length;
  const bizSum = bizPerUser.reduce((a, r) => a + (Number(r.n) || 0), 0);

  const logoUsers = await scalar(
    db,
    `SELECT COUNT(DISTINCT user_id) AS c FROM doc_businesses
     WHERE json_extract(data_json, '$.logo_enabled') = 1
        OR (json_extract(data_json, '$.logo_b64') IS NOT NULL
            AND length(json_extract(data_json, '$.logo_b64')) > 20)`
  );

  const emailCopyRows = await rows(
    db,
    `SELECT LOWER(COALESCE(json_extract(data_json, '$.email_self_copy'), 'unset')) AS m, COUNT(*) AS c
     FROM doc_settings
     GROUP BY m`
  );
  const emailSelfCopy = Object.fromEntries(
    emailCopyRows.map((r) => [String(r.m), Number(r.c) || 0])
  );

  const outboxSent = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM email_outbox WHERE status = 'sent'"
  );
  const outboxFailed = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM email_outbox WHERE status = 'failed'"
  );
  const outboxPending = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM email_outbox WHERE status IN ('pending', 'generating_pdf')"
  );

  const devicePerUser = await rows(
    db,
    `SELECT user_id, COUNT(*) AS n FROM account_devices GROUP BY user_id`
  );
  const deviceCounts = devicePerUser.map((r) => Number(r.n) || 0);
  const deviceSum = deviceCounts.reduce((a, b) => a + b, 0);
  const multiDevice = deviceCounts.filter((n) => n > 1).length;
  const platformRows = await rows(
    db,
    `SELECT platform, COUNT(*) AS c FROM account_devices GROUP BY platform`
  );
  const platforms = Object.fromEntries(
    platformRows.map((r) => [String(r.platform), Number(r.c) || 0])
  );

  const accountsWithDevices = devicePerUser.length;

  return {
    generated_at: new Date().toISOString(),
    accounts: {
      total: accountsTotal,
      active_paid: accountsActive,
      pending_payment: accountsPending,
      tier_local: tierLocal,
      tier_cloud: tierCloud,
      cloud_with_docs: cloudUsersWithDocs,
    },
    subscription: {
      ever_subscribed: subscribed,
      cancel_scheduled: cancelScheduled,
      unsubscribed,
      cancel_scheduled_pct: pct(cancelScheduled, subscribed),
      churn_pct: pct(unsubscribed, subscribed),
      median_tenure_days: medianTenure,
    },
    invoices: {
      total: invSum,
      avg_per_cloud_account: avg(invSum, cloudUsersWithDocs || 1),
      accounts_with_sent: accountsWithSent,
      accounts_with_sent_pct: pct(accountsWithSent, cloudUsersWithDocs),
      buckets: invBuckets,
      due_rule_types: dueTypes,
      settings_due_defaults: settingsDueDefaults,
      sent_ish_count: sentInvoices,
    },
    customers: {
      total: customersTotal,
      avg_per_cloud_account: avg(custSum, cloudUsersWithDocs || 1),
      buckets: custBuckets,
      created_via_inline: inlineCustomers,
      created_via_list_or_unknown: listCustomers,
      inline_pct: pct(inlineCustomers, customersTotal),
    },
    businesses: {
      total: bizSum,
      avg_per_cloud_account: avg(bizSum, cloudUsersWithDocs || 1),
      multi_business_accounts: multiBiz,
      multi_business_pct: pct(multiBiz, cloudUsersWithDocs),
      accounts_with_logo: logoUsers,
      logo_adoption_pct: pct(logoUsers, cloudUsersWithDocs),
    },
    email: {
      self_copy: emailSelfCopy,
      outbox_sent: outboxSent,
      outbox_failed: outboxFailed,
      outbox_pending: outboxPending,
      send_success_pct: pct(outboxSent, outboxSent + outboxFailed),
    },
    devices: {
      accounts_reporting: accountsWithDevices,
      avg_per_reporting_account: avg(deviceSum, accountsWithDevices || 1),
      multi_device_accounts: multiDevice,
      multi_device_pct: pct(multiDevice, accountsWithDevices),
      platforms,
    },
  };
}
