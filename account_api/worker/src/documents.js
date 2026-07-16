import { SignJWT, jwtVerify } from "jose";
import { jwtSecretBytes } from "./jwt_secret.js";
import { buildInvoicePdf } from "./invoice_pdf.js";
import {
  buildInvoiceEmailContent,
  emailCopyPrefsFromSettings,
} from "./invoice_email.js";
import {
  decodePdfB64,
  MAX_MIGRATE_BYTES,
  readJsonLimited,
  validateSyncMutations,
} from "./upload_security.js";

const GUEST_TTL_DAYS = 30;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status) {
  return json({ error: message }, status);
}

function nowIso() {
  return new Date().toISOString();
}

/** Chunked base64 — avoid stack overflow from String.fromCharCode(...largeBuffer). */
function bytesToBase64(bytes) {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const chunk = 0x8000;
  let binary = "";
  for (let i = 0; i < u8.length; i += chunk) {
    binary += String.fromCharCode(...u8.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function invoiceKey(number) {
  return String(number).padStart(8, "0");
}

/** Storage key: invoice_id when present; else legacy padded invoice_number. */
function storageKeyFromInvoice(invoice) {
  const id = String(invoice?.invoice_id || "").trim();
  if (id) return id;
  const number = Number(invoice?.invoice_number);
  if (!Number.isFinite(number) || number < 1) throw new Error("Invalid invoice number");
  return invoiceKey(number);
}

function mutationInvoiceKey(payload) {
  const id = String(payload?.invoice_id || "").trim();
  if (id) return id;
  if (payload?.invoice_number != null && payload.invoice_number !== "") {
    return invoiceKey(Number(payload.invoice_number));
  }
  throw new Error("invoice_id or invoice_number required");
}

async function resolveInvoiceLookup(db, userId, pathSeg) {
  const seg = String(pathSeg || "").trim();
  if (!seg) return null;
  let row = await dbInvoice(db, userId, seg);
  if (row) return { key: seg, row };
  if (/^\d+$/.test(seg)) {
    const padded = invoiceKey(Number(seg));
    if (padded !== seg) {
      row = await dbInvoice(db, userId, padded);
      if (row) return { key: padded, row };
    }
    const map = await loadInvoicesMap(db, userId);
    let best = null;
    for (const [key, inv] of Object.entries(map)) {
      if (Number(inv.invoice_number) !== Number(seg)) continue;
      if (inv.deleted_at) continue;
      if (
        !best ||
        String(inv.updated_at || inv.invoice_date || "") >
          String(best.inv.updated_at || best.inv.invoice_date || "")
      ) {
        best = { key, inv };
      }
    }
    if (best) {
      row = await dbInvoice(db, userId, best.key);
      if (row) return { key: best.key, row };
    }
  }
  return null;
}

export function storageTierFromSubscription(sub) {
  const item = sub?.items?.data?.[0];
  const meta = item?.price?.metadata || {};
  const tier = (meta.storage_tier || meta.tier || "local").toLowerCase();
  return tier === "cloud" ? "cloud" : "local";
}

export function entitlementsPlatforms(storageTier) {
  const cloud = storageTier === "cloud";
  return { desktop: true, mobile: cloud };
}

export async function resolveStorageTier(db, stripe, user) {
  const access = await loadCloudAccess(db, stripe, user);
  return access.tier;
}

/** One Stripe subscriptions.list → tier + active. */
export async function loadCloudAccess(db, stripe, user) {
  if (!user?.stripe_customer_id || !stripe) {
    const tier = user?.storage_tier === "cloud" ? "cloud" : "local";
    return { tier, active: false, listMs: 0 };
  }
  const t0 = Date.now();
  const subs = await stripe.subscriptions.list({
    customer: user.stripe_customer_id,
    status: "all",
    limit: 5,
  });
  const listMs = Date.now() - t0;
  for (const sub of subs.data) {
    if (sub.status === "active" || sub.status === "trialing") {
      const tier = storageTierFromSubscription(sub);
      if (tier !== user.storage_tier) {
        await db
          .prepare("UPDATE users SET storage_tier = ? WHERE id = ?")
          .bind(tier, user.id)
          .run();
      }
      return { tier, active: true, listMs, status: sub.status };
    }
  }
  return {
    tier: user?.storage_tier === "cloud" ? "cloud" : "local",
    active: false,
    listMs,
  };
}

async function requireCloudUser(auth, env, stripe) {
  if (auth.cloudAccess?.tier === "cloud") {
    return { tier: "cloud", perf: { requireCloudUserMs: 0, reusedMobileGate: true } };
  }
  const access = await loadCloudAccess(env.DB, stripe, auth.user);
  if (access.tier !== "cloud") {
    return {
      error: textError("Cloud storage tier required.", 403),
      perf: { requireCloudUserMs: access.listMs },
    };
  }
  auth.cloudAccess = access;
  return { tier: access.tier, perf: { requireCloudUserMs: access.listMs } };
}

function documentsBucket(env) {
  return env.DOCUMENTS || env.RELEASES;
}

function pdfR2Key(userId, invoiceKeyStr) {
  return `user-docs/${userId}/invoices/${invoiceKeyStr}.pdf`;
}

async function loadBusinessesMap(db, userId) {
  const rows = await db
    .prepare("SELECT name, data_json, revision, updated_at FROM doc_businesses WHERE user_id = ?")
    .bind(userId)
    .all();
  const out = {};
  for (const row of rows.results || []) {
    try {
      out[row.name] = JSON.parse(row.data_json);
    } catch {
      out[row.name] = {};
    }
  }
  return out;
}

async function loadCustomersMap(db, userId) {
  const rows = await db
    .prepare("SELECT name, data_json, revision, updated_at FROM doc_customers WHERE user_id = ?")
    .bind(userId)
    .all();
  const out = {};
  for (const row of rows.results || []) {
    try {
      out[row.name] = JSON.parse(row.data_json);
    } catch {
      out[row.name] = {};
    }
  }
  return out;
}

/** Prefer saved customer; fall back to address/email snapshotted on the invoice (one-off customers). */
function customerForInvoice(invoice, customers) {
  const name = String(invoice?.customer_name || "").trim();
  const saved = name && customers ? customers[name] : null;
  if (saved && typeof saved === "object") {
    return {
      ...saved,
      email: invoice.customer_email || saved.email || "",
      abn: invoice.customer_abn || saved.abn || "",
    };
  }
  return {
    email: invoice?.customer_email || "",
    abn: invoice?.customer_abn || "",
    address_line1: invoice?.address_line1 || invoice?.customer_address_line1 || "",
    address_line2: invoice?.address_line2 || invoice?.customer_address_line2 || "",
    suburb: invoice?.suburb || invoice?.customer_suburb || "",
    state: invoice?.state || invoice?.customer_state || "",
    postcode: invoice?.postcode || invoice?.customer_postcode || "",
  };
}

async function loadInvoicesMap(db, userId) {
  const rows = await db
    .prepare(
      "SELECT invoice_key, data_json, pdf_status, pdf_r2_key, revision, updated_at FROM doc_invoices WHERE user_id = ?"
    )
    .bind(userId)
    .all();
  const out = {};
  for (const row of rows.results || []) {
    try {
      const inv = JSON.parse(row.data_json);
      inv.invoice_id = String(inv.invoice_id || row.invoice_key);
      inv.pdf_status = row.pdf_status || inv.pdf_status || "pending";
      inv.pdf_r2_key = row.pdf_r2_key;
      out[row.invoice_key] = inv;
    } catch {
      /* skip */
    }
  }
  return out;
}

async function loadSettings(db, userId) {
  const row = await db
    .prepare("SELECT data_json FROM doc_settings WHERE user_id = ?")
    .bind(userId)
    .first();
  if (!row) return {};
  try {
    return JSON.parse(row.data_json);
  } catch {
    return {};
  }
}

async function upsertBusinesses(db, userId, businesses) {
  const ts = nowIso();
  for (const [name, data] of Object.entries(businesses || {})) {
    await db
      .prepare(
        `INSERT INTO doc_businesses (user_id, name, data_json, revision, updated_at)
         VALUES (?, ?, ?, 1, ?)
         ON CONFLICT(user_id, name) DO UPDATE SET
           data_json = excluded.data_json,
           revision = revision + 1,
           updated_at = excluded.updated_at`
      )
      .bind(userId, name, JSON.stringify(data), ts)
      .run();
  }
}

async function upsertCustomers(db, userId, customers) {
  const ts = nowIso();
  for (const [name, data] of Object.entries(customers || {})) {
    await db
      .prepare(
        `INSERT INTO doc_customers (user_id, name, data_json, revision, updated_at)
         VALUES (?, ?, ?, 1, ?)
         ON CONFLICT(user_id, name) DO UPDATE SET
           data_json = excluded.data_json,
           revision = revision + 1,
           updated_at = excluded.updated_at`
      )
      .bind(userId, name, JSON.stringify(data), ts)
      .run();
  }
}

async function upsertSettings(db, userId, settings) {
  const existing = await loadSettings(db, userId);
  const merged = { ...existing, ...(settings || {}) };
  const ts = nowIso();
  await db
    .prepare(
      `INSERT INTO doc_settings (user_id, data_json, revision, updated_at)
       VALUES (?, ?, 1, ?)
       ON CONFLICT(user_id) DO UPDATE SET data_json = excluded.data_json, revision = revision + 1, updated_at = excluded.updated_at`
    )
    .bind(userId, JSON.stringify(merged), ts)
    .run();
}

async function deleteCustomer(db, userId, name) {
  await db.prepare("DELETE FROM doc_customers WHERE user_id = ? AND name = ?").bind(userId, name).run();
}

async function softDeleteInvoice(db, userId, payload) {
  const key = mutationInvoiceKey(payload);
  const row = await dbInvoice(db, userId, key);
  if (!row) throw new Error("Invoice not found");
  const inv = JSON.parse(row.data_json);
  inv.invoice_id = String(inv.invoice_id || key);
  inv.deleted_at = nowIso();
  const ts = nowIso();
  await db
    .prepare(
      `UPDATE doc_invoices SET data_json = ?, revision = revision + 1, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
    )
    .bind(JSON.stringify(inv), ts, userId, key)
    .run();
}

async function upsertInvoice(db, userId, invoice) {
  const number = Number(invoice.invoice_number);
  if (!Number.isFinite(number) || number < 1) throw new Error("Invalid invoice number");
  const key = storageKeyFromInvoice(invoice);
  const payload = {
    ...invoice,
    invoice_id: key,
    invoice_number: number,
    pdf_status: "pending",
  };
  delete payload.pdf_r2_key;
  const ts = nowIso();
  await db
    .prepare(
      `INSERT INTO doc_invoices (user_id, invoice_key, invoice_number, data_json, revision, updated_at, pdf_status, pdf_r2_key)
       VALUES (?, ?, ?, ?, 1, ?, 'pending', NULL)
       ON CONFLICT(user_id, invoice_key) DO UPDATE SET
         data_json = excluded.data_json,
         invoice_number = excluded.invoice_number,
         revision = revision + 1,
         updated_at = excluded.updated_at,
         pdf_status = 'pending',
         pdf_r2_key = NULL`
    )
    .bind(userId, key, number, JSON.stringify(payload), ts)
    .run();
  return key;
}

async function updateInvoiceStatus(db, userId, payload, status) {
  const key = mutationInvoiceKey(
    typeof payload === "object" && payload !== null
      ? payload
      : { invoice_number: payload }
  );
  const row = await db
    .prepare("SELECT data_json FROM doc_invoices WHERE user_id = ? AND invoice_key = ?")
    .bind(userId, key)
    .first();
  if (!row) return false;
  const inv = JSON.parse(row.data_json);
  inv.invoice_id = String(inv.invoice_id || key);
  inv.status = status;
  const ts = nowIso();
  await db
    .prepare(
      `UPDATE doc_invoices SET data_json = ?, revision = revision + 1, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
    )
    .bind(JSON.stringify(inv), ts, userId, key)
    .run();
  return true;
}

/** Generate invoice PDF bytes (pdf-lib). */
async function buildInvoicePdfBytes(invoice, business = {}, customer = {}) {
  return buildInvoicePdf(invoice, business, customer);
}

export async function generateInvoicePdf(env, userId, invoiceRef) {
  let key;
  let row;
  if (typeof invoiceRef === "object" && invoiceRef !== null) {
    key = mutationInvoiceKey(invoiceRef);
    row = await dbInvoice(env.DB, userId, key);
  } else if (typeof invoiceRef === "string" && !/^\d+$/.test(invoiceRef)) {
    key = invoiceRef;
    row = await dbInvoice(env.DB, userId, key);
  } else {
    const looked = await resolveInvoiceLookup(env.DB, userId, String(invoiceRef));
    if (!looked) throw new Error("Invoice not found");
    key = looked.key;
    row = looked.row;
  }
  if (!row) throw new Error("Invoice not found");
  const invoice = JSON.parse(row.data_json);
  invoice.invoice_id = String(invoice.invoice_id || key);
  const businesses = await loadBusinessesMap(env.DB, userId);
  const customers = await loadCustomersMap(env.DB, userId);
  const business = businesses[invoice.business_name] || {};
  const customer = customerForInvoice(invoice, customers);
  const bucket = documentsBucket(env);
  if (!bucket) throw new Error("Document storage not configured");
  const r2Key = pdfR2Key(userId, key);
  const bytes = await buildInvoicePdfBytes(invoice, business, customer);
  await bucket.put(r2Key, bytes, {
    httpMetadata: { contentType: "application/pdf" },
  });
  const numPad = invoiceKey(Number(invoice.invoice_number) || 0);
  const filename = `Invoice_${numPad}_${invoice.invoice_date || "draft"}.pdf`;
  invoice.filename = filename;
  invoice.pdf_status = "ready";
  const ts = nowIso();
  await env.DB.prepare(
    `UPDATE doc_invoices SET data_json = ?, pdf_status = 'ready', pdf_r2_key = ?, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
  )
    .bind(JSON.stringify(invoice), r2Key, ts, userId, key)
    .run();
  return { filename, r2Key, invoice_key: key };
}

async function dbInvoice(db, userId, key) {
  return db
    .prepare("SELECT * FROM doc_invoices WHERE user_id = ? AND invoice_key = ?")
    .bind(userId, key)
    .first();
}

export async function enqueueEmailSend(env, userId, invoiceRef, userEmail) {
  const payload =
    typeof invoiceRef === "object" && invoiceRef !== null
      ? invoiceRef
      : { invoice_number: invoiceRef };
  const key = mutationInvoiceKey(payload);
  const row = await dbInvoice(env.DB, userId, key);
  if (!row) throw new Error("Invoice not found");
  const inv = JSON.parse(row.data_json);
  const invoiceNumber = Number(inv.invoice_number || payload.invoice_number);
  const id = crypto.randomUUID();
  const ts = nowIso();
  try {
    await env.DB.prepare(
      `INSERT INTO email_outbox (id, user_id, invoice_number, invoice_key, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)`
    )
      .bind(id, userId, invoiceNumber, key, ts, ts)
      .run();
  } catch {
    await env.DB.prepare(
      `INSERT INTO email_outbox (id, user_id, invoice_number, status, created_at, updated_at)
       VALUES (?, ?, ?, 'pending', ?, ?)`
    )
      .bind(id, userId, invoiceNumber, ts, ts)
      .run();
  }
  await updateInvoiceStatus(env.DB, userId, { invoice_id: key, invoice_number: invoiceNumber }, "send_queued");

  const runOutbox = () =>
    processEmailOutbox(env, userId, userEmail).catch((err) => {
      console.log(
        JSON.stringify({
          action: "processEmailOutbox.bg_error",
          error: String(err?.message || err),
        })
      );
    });

  if (env._executionCtx?.waitUntil) {
    env._executionCtx.waitUntil(runOutbox());
    return {
      id,
      status: "send_queued",
      invoice_key: key,
      invoice_number: invoiceNumber,
      async: true,
    };
  }

  const processed = await processEmailOutbox(env, userId, userEmail);
  const forThis =
    (processed.items || []).find((item) => item.outbox_id === id) || processed.items?.[0] || null;
  return {
    id,
    status: forThis?.final_status || "send_queued",
    invoice_key: key,
    invoice_number: invoiceNumber,
  };
}

export async function processEmailOutbox(env, userId, userEmail) {
  const rows = await env.DB.prepare(
    `SELECT * FROM email_outbox WHERE user_id = ? AND status IN ('pending', 'generating_pdf', 'failed') ORDER BY created_at LIMIT 10`
  )
    .bind(userId)
    .all();
  const provider =
    (env.EMAIL_PROVIDER || "").trim() || (env.RESEND_API_KEY ? "resend" : "log");
  const hasResendKey = Boolean(env.RESEND_API_KEY);
  const settings = await loadSettings(env.DB, userId);
  const businesses = await loadBusinessesMap(env.DB, userId);
  const customers = await loadCustomersMap(env.DB, userId);
  const copyPrefs = emailCopyPrefsFromSettings(settings);
  const items = [];
  for (const row of rows.results || []) {
    const ts = nowIso();
    const item = {
      outbox_id: row.id,
      invoice_number: row.invoice_number,
      invoice_key: row.invoice_key || null,
      branch: null,
      pdf_was_ready: null,
      has_customer_email: false,
      resend_status: null,
      final_status: null,
      error: null,
      cc_self: copyPrefs.ccSelf,
      bcc_self: copyPrefs.bccSelf,
      self_copy_mode: copyPrefs.mode,
    };
    try {
      let key = String(row.invoice_key || "").trim();
      let invRow = key ? await dbInvoice(env.DB, userId, key) : null;
      if (!invRow) {
        const looked = await resolveInvoiceLookup(env.DB, userId, String(row.invoice_number));
        if (!looked) {
          item.branch = "invoice_not_found";
          item.final_status = "skipped";
          items.push(item);
          continue;
        }
        key = looked.key;
        invRow = looked.row;
      }
      item.invoice_key = key;
      item.pdf_was_ready = invRow.pdf_status === "ready";
      if (invRow.pdf_status !== "ready") {
        await env.DB.prepare(`UPDATE email_outbox SET status = 'generating_pdf', updated_at = ? WHERE id = ?`)
          .bind(ts, row.id)
          .run();
        const tPdf = Date.now();
        await generateInvoicePdf(env, userId, { invoice_id: key });
        item.pdf_generate_ms = Date.now() - tPdf;
        invRow = await dbInvoice(env.DB, userId, key);
      } else {
        item.pdf_generate_ms = 0;
      }
      const invoice = JSON.parse(invRow.data_json);
      const customer = customerForInvoice(invoice, customers);
      const customerEmail = String(
        invoice.customer_email || customer.email || ""
      ).trim();
      item.has_customer_email = Boolean(customerEmail);
      if (!customerEmail && provider !== "log") {
        throw new Error("Customer email required");
      }
      const composed = buildInvoiceEmailContent({
        invoice,
        customer,
        settings,
        businesses,
      });
      const bucket = documentsBucket(env);
      const pdfObj = invRow.pdf_r2_key ? await bucket.get(invRow.pdf_r2_key) : null;
      const pdfBytes = pdfObj ? await pdfObj.arrayBuffer() : null;
      const selfEmail = String(userEmail || "").trim();
      const cc = copyPrefs.ccSelf && selfEmail ? [selfEmail] : [];
      const bcc = copyPrefs.bccSelf && selfEmail ? [selfEmail] : [];
      if (provider === "log") {
        item.branch = "log_provider_no_resend";
        item.resend_ms = 0;
        console.log(
          JSON.stringify({
            action: "send_invoice_email",
            to: customerEmail || "(missing)",
            cc,
            bcc,
            subject: composed.subject,
            invoice_number: row.invoice_number,
            pdf_bytes: pdfBytes ? pdfBytes.byteLength : 0,
          })
        );
      } else if (env.RESEND_API_KEY && customerEmail) {
        item.branch = "resend";
        const bytes = pdfBytes ? new Uint8Array(pdfBytes) : null;
        item.pdf_bytes = bytes ? bytes.length : 0;
        const b64 = bytes && bytes.length ? bytesToBase64(bytes) : "";
        const payload = {
          from: env.EMAIL_FROM || "invoices@frogswork.com",
          to: [customerEmail],
          subject: composed.subject,
          text: composed.text,
          html: composed.html,
          attachments: b64
            ? [{ filename: composed.filename || "invoice.pdf", content: b64 }]
            : [],
        };
        if (cc.length) payload.cc = cc;
        if (bcc.length) payload.bcc = bcc;
        const tResend = Date.now();
        const res = await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.RESEND_API_KEY}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        item.resend_ms = Date.now() - tResend;
        item.resend_status = res.status;
        if (!res.ok) {
          const body = await res.text();
          throw new Error(body || `Resend error ${res.status}`);
        }
      } else {
        item.branch = "no_resend_path";
        throw new Error(
          !env.RESEND_API_KEY
            ? "Email provider not configured (missing RESEND_API_KEY)."
            : "Customer email required"
        );
      }
      await env.DB.prepare(
        `UPDATE email_outbox SET status = 'sent', updated_at = ?, attempts = attempts + 1 WHERE id = ?`
      )
        .bind(ts, row.id)
        .run();
      await updateInvoiceStatus(
        env.DB,
        userId,
        { invoice_id: key, invoice_number: row.invoice_number },
        "sent"
      );
      item.final_status = "sent";
    } catch (exc) {
      item.error = String(exc.message || exc).slice(0, 300);
      item.final_status = "send_failed";
      await env.DB.prepare(
        `UPDATE email_outbox SET status = 'failed', last_error = ?, updated_at = ?, attempts = attempts + 1 WHERE id = ?`
      )
        .bind(String(exc.message || exc), ts, row.id)
        .run();
      const failKey = String(row.invoice_key || "").trim() || invoiceKey(row.invoice_number);
      await updateInvoiceStatus(
        env.DB,
        userId,
        { invoice_id: failKey, invoice_number: row.invoice_number },
        "send_failed"
      );
    }
    items.push(item);
  }
  return { provider, hasResendKey, items };
}

async function applyMutation(db, userId, mutation, env, userEmail) {
  const { type, payload } = mutation;
  switch (type) {
    case "upsert_business":
      await upsertBusinesses(db, userId, payload.businesses);
      return { ok: true };
    case "upsert_customer":
      await upsertCustomers(db, userId, payload.customers);
      return { ok: true };
    case "delete_customer":
      await deleteCustomer(db, userId, payload.name);
      return { ok: true };
    case "upsert_settings":
      await upsertSettings(db, userId, payload.settings);
      return { ok: true };
    case "delete_invoice":
      await softDeleteInvoice(db, userId, payload);
      return { ok: true };
    case "create_invoice": {
      const key = await upsertInvoice(db, userId, payload.invoice);
      if (payload.prepare_pdf && env?._executionCtx?.waitUntil) {
        env._executionCtx.waitUntil(
          generateInvoicePdf(env, userId, { invoice_id: key }).catch((err) => {
            console.log(
              JSON.stringify({
                action: "prepare_pdf.bg_error",
                error: String(err?.message || err),
              })
            );
          })
        );
      }
      return { ok: true, invoice_key: key };
    }
    case "update_invoice_status":
      await updateInvoiceStatus(db, userId, payload, payload.status);
      return { ok: true };
    case "enqueue_email_send":
      return enqueueEmailSend(env, userId, payload, userEmail);
    default:
      return { ok: false, error: `Unknown mutation: ${type}` };
  }
}

export async function handleDocumentsRoute(
  request,
  env,
  path,
  auth,
  stripe,
  subscriptionStatus,
  executionCtx = null
) {
  if (executionCtx) env._executionCtx = executionCtx;
  const cloud = await requireCloudUser(auth, env, stripe);
  if (cloud.error) return cloud.error;
  const userId = auth.user.id;

  if (path === "/documents/bootstrap" && request.method === "GET") {
    const businesses = await loadBusinessesMap(env.DB, userId);
    const customers = await loadCustomersMap(env.DB, userId);
    const invoices = await loadInvoicesMap(env.DB, userId);
    const settings = await loadSettings(env.DB, userId);
    return json({ businesses, customers, invoices, settings });
  }

  if (path === "/documents/migrate" && request.method === "POST") {
    let body = {};
    try {
      body = await readJsonLimited(request, MAX_MIGRATE_BYTES);
    } catch (exc) {
      return textError(String(exc.message || exc), 400);
    }
    if (body.businesses) await upsertBusinesses(env.DB, userId, body.businesses);
    if (body.customers) await upsertCustomers(env.DB, userId, body.customers);
    if (body.invoices) {
      for (const inv of Object.values(body.invoices)) {
        await upsertInvoice(env.DB, userId, inv);
      }
    }
    if (body.settings) {
      const ts = nowIso();
      await env.DB.prepare(
        `INSERT INTO doc_settings (user_id, data_json, revision, updated_at)
         VALUES (?, ?, 1, ?)
         ON CONFLICT(user_id) DO UPDATE SET data_json = excluded.data_json, revision = revision + 1, updated_at = excluded.updated_at`
      )
        .bind(userId, JSON.stringify(body.settings), ts)
        .run();
    }
    return json({
      ok: true,
      counts: {
        businesses: Object.keys(body.businesses || {}).length,
        customers: Object.keys(body.customers || {}).length,
        invoices: Object.keys(body.invoices || {}).length,
      },
    });
  }

  if (path === "/documents/sync" && request.method === "POST") {
    let body = {};
    try {
      body = await readJsonLimited(request, MAX_MIGRATE_BYTES);
      validateSyncMutations(body.mutations || []);
    } catch (exc) {
      return textError(String(exc.message || exc), 400);
    }
    const mutations = body.mutations || [];
    const results = [];
    const errors = [];
    let subActive =
      typeof auth.cloudAccess?.active === "boolean" ? auth.cloudAccess.active : null;
    for (const mutation of mutations) {
      if (mutation.type === "enqueue_email_send") {
        if (subActive === null) {
          const sub = await subscriptionStatus(stripe, auth.user.stripe_customer_id);
          subActive = sub.active;
        }
        if (!subActive) {
          errors.push({
            mutation,
            error: "Active subscription required for automatic email send.",
          });
          continue;
        }
      }
      try {
        const result = await applyMutation(
          env.DB,
          userId,
          mutation,
          env,
          auth.user.email
        );
        results.push(result);
      } catch (exc) {
        errors.push({ mutation, error: String(exc.message || exc) });
      }
    }
    return json({ ok: errors.length === 0, results, errors });
  }

  const pdfMatch = path.match(/^\/documents\/invoices\/([^/]+)\/pdf$/);
  if (pdfMatch && request.method === "GET") {
    const looked = await resolveInvoiceLookup(env.DB, userId, pdfMatch[1]);
    if (!looked) return textError("Invoice not found", 404);
    let { key, row } = looked;
    if (row.pdf_status !== "ready") {
      await generateInvoicePdf(env, userId, { invoice_id: key });
      row = await dbInvoice(env.DB, userId, key);
    }
    const bucket = documentsBucket(env);
    if (!row?.pdf_r2_key || !bucket) return textError("PDF not available", 404);
    const obj = await bucket.get(row.pdf_r2_key);
    if (!obj) return textError("PDF not found", 404);
    const buf = await obj.arrayBuffer();
    const inv = JSON.parse(row.data_json);
    const b64 = bytesToBase64(buf);
    return json({ filename: inv.filename, content_b64: b64, invoice_key: key });
  }

  const sendMatch = path.match(/^\/documents\/invoices\/([^/]+)\/send$/);
  if (sendMatch && request.method === "POST") {
    const sub = await subscriptionStatus(stripe, auth.user.stripe_customer_id);
    if (!sub.active) {
      return textError("Active subscription required for automatic email send.", 403);
    }
    const looked = await resolveInvoiceLookup(env.DB, userId, sendMatch[1]);
    if (!looked) return textError("Invoice not found", 404);
    const { key } = looked;
    let body = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }
    if (body.pdf_b64) {
      let binary;
      try {
        binary = decodePdfB64(body.pdf_b64);
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
      const bucket = documentsBucket(env);
      const r2Key = pdfR2Key(userId, key);
      await bucket.put(r2Key, binary, {
        httpMetadata: { contentType: "application/pdf" },
      });
      const row = await dbInvoice(env.DB, userId, key);
      if (row) {
        const inv = JSON.parse(row.data_json);
        inv.pdf_status = "ready";
        inv.invoice_id = String(inv.invoice_id || key);
        await env.DB.prepare(
          `UPDATE doc_invoices SET pdf_status = 'ready', pdf_r2_key = ?, data_json = ?, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
        )
          .bind(r2Key, JSON.stringify(inv), nowIso(), userId, key)
          .run();
      }
    }
    return enqueueEmailSend(env, userId, { invoice_id: key }, auth.user.email);
  }

  const genMatch = path.match(/^\/documents\/invoices\/([^/]+)\/generate$/);
  if (genMatch && request.method === "POST") {
    const looked = await resolveInvoiceLookup(env.DB, userId, genMatch[1]);
    if (!looked) return textError("Invoice not found", 404);
    const result = await generateInvoicePdf(env, userId, { invoice_id: looked.key });
    return json({ ok: true, ...result });
  }

  return null;
}

function emptyGuestWorkspace() {
  return { businesses: {}, customers: {}, invoices: {}, settings: {} };
}

async function loadGuestWorkspace(db, guestId) {
  const row = await db
    .prepare("SELECT data_json, expires_at FROM guest_workspaces WHERE guest_id = ?")
    .bind(guestId)
    .first();
  if (!row) throw new Error("Guest workspace not found");
  if (new Date(row.expires_at) < new Date()) throw new Error("Guest trial expired");
  try {
    const data = JSON.parse(row.data_json || "{}");
    return { ...emptyGuestWorkspace(), ...data };
  } catch {
    return emptyGuestWorkspace();
  }
}

async function saveGuestWorkspace(db, guestId, data) {
  await db
    .prepare("UPDATE guest_workspaces SET data_json = ? WHERE guest_id = ?")
    .bind(JSON.stringify(data), guestId)
    .run();
}

function applyGuestMutation(workspace, mutation) {
  const { type, payload } = mutation;
  switch (type) {
    case "upsert_business":
      Object.assign(workspace.businesses, payload.businesses || {});
      return { ok: true };
    case "upsert_customer":
      Object.assign(workspace.customers, payload.customers || {});
      return { ok: true };
    case "delete_customer": {
      const name = payload.name;
      if (name) delete workspace.customers[name];
      return { ok: true };
    }
    case "create_invoice": {
      const inv = payload.invoice || {};
      const key = storageKeyFromInvoice(inv);
      workspace.invoices[key] = {
        ...inv,
        invoice_id: key,
        pdf_status: "pending",
      };
      return { ok: true, invoice_key: key };
    }
    case "update_invoice_status": {
      const key = mutationInvoiceKey(payload);
      if (workspace.invoices[key]) {
        workspace.invoices[key].status = payload.status;
      }
      return { ok: true };
    }
    case "upsert_settings":
      workspace.settings = { ...workspace.settings, ...(payload.settings || {}) };
      return { ok: true };
    case "delete_invoice": {
      const key = mutationInvoiceKey(payload);
      if (workspace.invoices[key]) {
        workspace.invoices[key].deleted_at = nowIso();
      }
      return { ok: true };
    }
    case "enqueue_email_send": {
      const key = mutationInvoiceKey(payload);
      if (workspace.invoices[key]) {
        workspace.invoices[key].status = "sent";
        workspace.invoices[key].pdf_status = "ready";
      }
      return { ok: true, status: "sent", note: "Guest trial — email not sent. Upgrade to Cloud." };
    }
    default:
      return { ok: false, error: `Unknown mutation: ${type}` };
  }
}

export async function handleGuestDocumentsRoute(request, env, path, guestId) {
  if (path === "/documents/bootstrap" && request.method === "GET") {
    const ws = await loadGuestWorkspace(env.DB, guestId);
    return json({
      businesses: ws.businesses,
      customers: ws.customers,
      invoices: ws.invoices,
      settings: ws.settings,
    });
  }

  if (path === "/documents/migrate" && request.method === "POST") {
    let body = {};
    try {
      body = await readJsonLimited(request, MAX_MIGRATE_BYTES);
    } catch (exc) {
      return textError(String(exc.message || exc), 400);
    }
    const ws = await loadGuestWorkspace(env.DB, guestId);
    if (body.businesses) Object.assign(ws.businesses, body.businesses);
    if (body.customers) Object.assign(ws.customers, body.customers);
    if (body.invoices) Object.assign(ws.invoices, body.invoices);
    if (body.settings) ws.settings = { ...ws.settings, ...body.settings };
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ ok: true });
  }

  if (path === "/documents/sync" && request.method === "POST") {
    let body = {};
    try {
      body = await readJsonLimited(request, MAX_MIGRATE_BYTES);
      validateSyncMutations(body.mutations || []);
    } catch (exc) {
      return textError(String(exc.message || exc), 400);
    }
    const ws = await loadGuestWorkspace(env.DB, guestId);
    const results = [];
    const errors = [];
    for (const mutation of body.mutations || []) {
      try {
        results.push(applyGuestMutation(ws, mutation));
      } catch (exc) {
        errors.push({ mutation, error: String(exc.message || exc) });
      }
    }
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ ok: errors.length === 0, results, errors });
  }

  const pdfMatch = path.match(/^\/documents\/invoices\/([^/]+)\/pdf$/);
  if (pdfMatch && request.method === "GET") {
    const ws = await loadGuestWorkspace(env.DB, guestId);
    let key = String(pdfMatch[1] || "").trim();
    let inv = ws.invoices[key];
    if (!inv && /^\d+$/.test(key)) {
      const padded = invoiceKey(Number(key));
      inv = ws.invoices[padded];
      if (inv) key = padded;
      else {
        for (const [k, candidate] of Object.entries(ws.invoices || {})) {
          if (Number(candidate.invoice_number) === Number(key) && !candidate.deleted_at) {
            inv = candidate;
            key = k;
            break;
          }
        }
      }
    }
    if (!inv) return textError("Invoice not found", 404);
    const business = (ws.businesses || {})[inv.business_name] || {};
    const customer = (ws.customers || {})[inv.customer_name] || {};
    const bytes = await buildInvoicePdfBytes(inv, business, customer);
    const b64 = bytesToBase64(bytes);
    inv.pdf_status = "ready";
    inv.invoice_id = String(inv.invoice_id || key);
    ws.invoices[key] = inv;
    await saveGuestWorkspace(env.DB, guestId, ws);
    const numPad = invoiceKey(Number(inv.invoice_number) || 0);
    return json({
      filename: inv.filename || `Invoice_${numPad}.pdf`,
      content_b64: b64,
      invoice_key: key,
    });
  }

  const sendMatch = path.match(/^\/documents\/invoices\/([^/]+)\/send$/);
  if (sendMatch && request.method === "POST") {
    return textError(
      "Automatic email send requires a paid account. Use manual send or subscribe at frogswork.com.",
      403
    );
  }

  const genMatch = path.match(/^\/documents\/invoices\/([^/]+)\/generate$/);
  if (genMatch && request.method === "POST") {
    const ws = await loadGuestWorkspace(env.DB, guestId);
    let key = String(genMatch[1] || "").trim();
    if (!ws.invoices[key] && /^\d+$/.test(key)) {
      const padded = invoiceKey(Number(key));
      if (ws.invoices[padded]) key = padded;
    }
    if (!ws.invoices[key]) return textError("Invoice not found", 404);
    const inv = ws.invoices[key];
    const business = (ws.businesses || {})[inv.business_name] || {};
    const customer = (ws.customers || {})[inv.customer_name] || {};
    const bytes = await buildInvoicePdfBytes(inv, business, customer);
    ws.invoices[key].pdf_status = "ready";
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ ok: true, bytes: bytes.byteLength, invoice_key: key });
  }

  return null;
}

export async function issueGuestToken(env, guestId) {
  const secret = jwtSecretBytes(env);
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ sub: guestId, type: "guest" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + GUEST_TTL_DAYS * 24 * 60 * 60)
    .sign(secret);
}

export async function verifyGuestToken(env, token) {
  const secret = jwtSecretBytes(env);
  const { payload } = await jwtVerify(token, secret);
  if (payload.type !== "guest") throw new Error("wrong token type");
  return payload;
}

export async function handleGuestRoute(request, env, path) {
  if (path === "/guest/session" && request.method === "POST") {
    const guestId = crypto.randomUUID();
    const ts = nowIso();
    const expires = new Date(Date.now() + GUEST_TTL_DAYS * 24 * 60 * 60 * 1000).toISOString();
    await env.DB.prepare(
      `INSERT INTO guest_workspaces (guest_id, created_at, expires_at, data_json) VALUES (?, ?, ?, '{}')`
    )
      .bind(guestId, ts, expires)
      .run();
    const token = await issueGuestToken(env, guestId);
    return json({ guest_id: guestId, guest_token: token, expires_at: expires });
  }
  return null;
}
