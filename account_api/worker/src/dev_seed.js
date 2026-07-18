/** Dev-only: hard-purge cloud documents and seed demo data for subscribed accounts. */

function nowIso() {
  return new Date().toISOString();
}

function daysAgo(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function money(n) {
  return (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
}

function incGst(ex) {
  return money(Number(ex) * 1.1);
}

function documentsBucket(env) {
  return env.DOCUMENTS;
}

const SEED_BUSINESS = "Sam Chen — Garden & Property";

const SEED_BUSINESSES = {
  [SEED_BUSINESS]: {
    address: "Unit 4, 18 Kingsley Street\nFremantle WA 6160",
    abn: "51824793601",
    gst_registered: true,
    account_name: "Sam Chen",
    bsb: "016-001",
    acc: "284719",
    invoice_counter: 10,
  },
};

const SEED_CUSTOMERS = {
  "Harbour View Cafe": {
    address: "42 Marine Terrace\nFremantle WA 6160",
    abn: "87145632109",
    email: "accounts@harbourviewcafe.example",
  },
  "Pelican Point Strata": {
    address: "C/- Ace Body Corporate\nPO Box 120\nNorth Fremantle WA 6159",
    abn: "99631478523",
    email: "levies@pelicanpointstrata.example",
  },
  "West Coast Electrical": {
    address: "7 Forge Street\nO'Connor WA 6163",
    abn: "",
    email: "payables@westcoastelectrical.example",
  },
  "Margaret Nguyen": {
    address: "15 Pine Avenue\nPalmyra WA 6157",
    abn: "",
    email: "margaret.nguyen@example.com",
  },
  "Old Port Gallery": {
    address: "22 Henry Street\nFremantle WA 6160",
    abn: "53098741256",
    email: "",
  },
};

function simpleInvoice(id, number, customer, invDate, description, exGst, status, sentDate, paidDate) {
  const due = new Date(invDate + "T12:00:00Z");
  due.setUTCDate(due.getUTCDate() + 14);
  const dueIso = due.toISOString().slice(0, 10);
  const padded = String(number).padStart(8, "0");
  return {
    invoice_id: id,
    invoice_number: number,
    invoice_date: invDate,
    customer_name: customer,
    business_name: SEED_BUSINESS,
    description,
    amount_ex_gst: money(exGst),
    taxable_ex_gst: money(exGst),
    gst_free_ex_gst: "0.00",
    gst_amount: money(Number(exGst) * 0.1),
    total_inc_gst: incGst(exGst),
    gst_registered: true,
    line_items: [
      {
        description,
        quantity: 1,
        unit_amount_ex_gst: money(exGst),
        amount_ex_gst: money(exGst),
        gst_applicable: true,
        gst_free: false,
      },
    ],
    filename: `Invoice_${padded}_${invDate}.pdf`,
    status,
    sent_date: sentDate || null,
    paid_date: paidDate || null,
    due_date: dueIso,
    due_rule_type: "net_days",
    due_net_days: 14,
    pdf_status: "pending",
  };
}

function seedInvoiceSpecs() {
  return [
    simpleInvoice(crypto.randomUUID(), 1, "Harbour View Cafe", daysAgo(2), "Monthly grounds maintenance — March", 880, "not_sent"),
    simpleInvoice(crypto.randomUUID(), 2, "Margaret Nguyen", daysAgo(0), "Hedge trim and green waste removal", 420, "not_sent"),
    simpleInvoice(crypto.randomUUID(), 3, "Pelican Point Strata", daysAgo(18), "Common-area garden refresh", 2400, "sent", daysAgo(15)),
    simpleInvoice(crypto.randomUUID(), 4, "West Coast Electrical", daysAgo(10), "Site clearance before cable run", 650, "sent", daysAgo(8)),
    simpleInvoice(crypto.randomUUID(), 5, "Old Port Gallery", daysAgo(5), "Courtyard repaving prep and labour", 3200, "sent", daysAgo(3)),
    simpleInvoice(crypto.randomUUID(), 6, "Harbour View Cafe", daysAgo(52), "Irrigation repair and mulch top-up", 1500, "paid", daysAgo(49), daysAgo(35)),
    simpleInvoice(crypto.randomUUID(), 7, "Pelican Point Strata", daysAgo(28), "Seasonal prune — north garden bed", 990, "paid", daysAgo(26), daysAgo(12)),
    simpleInvoice(crypto.randomUUID(), 8, "Margaret Nguyen", daysAgo(14), "Lawn restoration and fertiliser", 450, "paid", daysAgo(12), daysAgo(2)),
  ];
}

function priceIdsFromEnv(env) {
  return {
    local: new Set(
      [env.STRIPE_PRICE_LOCAL_MONTHLY, env.STRIPE_PRICE_LOCAL_ANNUAL].filter(Boolean)
    ),
    cloud: new Set(
      [env.STRIPE_PRICE_CLOUD_MONTHLY, env.STRIPE_PRICE_CLOUD_ANNUAL].filter(Boolean)
    ),
  };
}

export function storageTierFromStripeSub(sub, env) {
  const prices = priceIdsFromEnv(env);
  const item = sub?.items?.data?.[0];
  const priceId = item?.price?.id || "";
  const meta = item?.price?.metadata || sub?.metadata || {};
  const metaTier = String(meta.storage_tier || meta.tier || "").toLowerCase();
  if (metaTier === "cloud" || metaTier === "local") return metaTier;
  if (prices.cloud.has(priceId)) return "cloud";
  if (prices.local.has(priceId)) return "local";
  return "local";
}

async function deleteR2Prefix(bucket, prefix) {
  if (!bucket) return 0;
  let deleted = 0;
  let cursor;
  do {
    const listed = await bucket.list({ prefix, cursor, limit: 1000 });
    for (const obj of listed.objects || []) {
      await bucket.delete(obj.key);
      deleted += 1;
    }
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
  return deleted;
}

export async function hardPurgeAllDocuments(env) {
  const db = env.DB;
  const counts = {};
  for (const [label, sql] of [
    ["doc_invoices", "DELETE FROM doc_invoices"],
    ["doc_businesses", "DELETE FROM doc_businesses"],
    ["doc_customers", "DELETE FROM doc_customers"],
    ["doc_settings", "DELETE FROM doc_settings"],
    ["email_outbox", "DELETE FROM email_outbox"],
    ["guest_workspaces", "DELETE FROM guest_workspaces"],
  ]) {
    const res = await db.prepare(sql).run();
    counts[label] = res.meta?.changes ?? 0;
  }
  const bucket = documentsBucket(env);
  counts.r2_deleted = await deleteR2Prefix(bucket, "user-docs/");
  return counts;
}

async function seedCloudUser(db, userId) {
  const ts = nowIso();
  for (const [name, data] of Object.entries(SEED_BUSINESSES)) {
    await db
      .prepare(
        `INSERT INTO doc_businesses (user_id, name, data_json, revision, updated_at)
         VALUES (?, ?, ?, 1, ?)`
      )
      .bind(userId, name, JSON.stringify(data), ts)
      .run();
  }
  for (const [name, data] of Object.entries(SEED_CUSTOMERS)) {
    await db
      .prepare(
        `INSERT INTO doc_customers (user_id, name, data_json, revision, updated_at)
         VALUES (?, ?, ?, 1, ?)`
      )
      .bind(userId, name, JSON.stringify(data), ts)
      .run();
  }
  const settings = {
    due_rule_type: "net_days",
    due_net_days: 14,
    welcome_complete: true,
    default_business: SEED_BUSINESS,
  };
  await db
    .prepare(
      `INSERT INTO doc_settings (user_id, data_json, revision, updated_at)
       VALUES (?, ?, 1, ?)`
    )
    .bind(userId, JSON.stringify(settings), ts)
    .run();

  const invoices = seedInvoiceSpecs();
  for (const inv of invoices) {
    await db
      .prepare(
        `INSERT INTO doc_invoices
         (user_id, invoice_key, invoice_number, data_json, revision, updated_at, pdf_status, pdf_r2_key)
         VALUES (?, ?, ?, ?, 1, ?, 'pending', NULL)`
      )
      .bind(userId, inv.invoice_id, inv.invoice_number, JSON.stringify(inv), ts)
      .run();
  }
  return {
    businesses: Object.keys(SEED_BUSINESSES).length,
    customers: Object.keys(SEED_CUSTOMERS).length,
    invoices: invoices.length,
  };
}

/**
 * Inspect Stripe for subscribed users, sync storage_tier, purge all docs, seed cloud accounts.
 */
export async function purgeAndSeedFromStripe(env, stripe) {
  const users = (
    await env.DB.prepare(
      `SELECT id, email, storage_tier, stripe_customer_id FROM users ORDER BY id`
    ).all()
  ).results || [];

  const subscriptionReport = [];
  for (const user of users) {
    if (!user.stripe_customer_id || !stripe) {
      subscriptionReport.push({
        id: user.id,
        email: user.email,
        stripe_customer_id: user.stripe_customer_id,
        stripe_status: null,
        stripe_tier: null,
        db_tier: user.storage_tier,
        active: false,
      });
      continue;
    }
    const subs = await stripe.subscriptions.list({
      customer: user.stripe_customer_id,
      status: "all",
      limit: 5,
    });
    let activeSub = null;
    for (const sub of subs.data || []) {
      if (sub.status === "active" || sub.status === "trialing") {
        activeSub = sub;
        break;
      }
    }
    const stripeTier = activeSub ? storageTierFromStripeSub(activeSub, env) : null;
    if (stripeTier && stripeTier !== user.storage_tier) {
      await env.DB.prepare("UPDATE users SET storage_tier = ? WHERE id = ?")
        .bind(stripeTier, user.id)
        .run();
    }
    subscriptionReport.push({
      id: user.id,
      email: user.email,
      stripe_customer_id: user.stripe_customer_id,
      stripe_status: activeSub?.status || (subs.data?.[0]?.status ?? "none"),
      stripe_tier: stripeTier,
      db_tier_before: user.storage_tier,
      db_tier_after: stripeTier || user.storage_tier,
      active: Boolean(activeSub),
      price_id: activeSub?.items?.data?.[0]?.price?.id || null,
    });
  }

  const purged = await hardPurgeAllDocuments(env);

  const seeded = [];
  for (const row of subscriptionReport) {
    if (!row.active || row.stripe_tier !== "cloud") continue;
    const counts = await seedCloudUser(env.DB, row.id);
    seeded.push({ user_id: row.id, email: row.email, ...counts });
  }

  return {
    ok: true,
    subscriptions: subscriptionReport,
    purged,
    seeded,
    note: "Local-tier accounts keep no cloud document seed (desktop/local storage only). Cloud accounts got demo businesses/customers/invoices (pdf_status pending — regenerate on View PDF).",
  };
}
