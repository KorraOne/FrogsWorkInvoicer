import { SignJWT, jwtVerify } from "jose";
import { jwtSecretBytes } from "./jwt_secret.js";
import { buildInvoicePdf } from "./invoice_pdf.js";
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

function invoiceKey(number) {
  return String(number).padStart(8, "0");
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
  if (!user?.stripe_customer_id || !stripe) {
    return user?.storage_tier === "cloud" ? "cloud" : "local";
  }
  const subs = await stripe.subscriptions.list({
    customer: user.stripe_customer_id,
    status: "all",
    limit: 5,
  });
  for (const sub of subs.data) {
    if (sub.status === "active" || sub.status === "trialing") {
      const tier = storageTierFromSubscription(sub);
      if (tier !== user.storage_tier) {
        await db
          .prepare("UPDATE users SET storage_tier = ? WHERE id = ?")
          .bind(tier, user.id)
          .run();
      }
      return tier;
    }
  }
  return user?.storage_tier === "cloud" ? "cloud" : "local";
}

async function requireCloudUser(auth, env, stripe) {
  const tier = await resolveStorageTier(env.DB, stripe, auth.user);
  if (tier !== "cloud") {
    return { error: textError("Cloud storage tier required.", 403) };
  }
  return { tier };
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

async function softDeleteInvoice(db, userId, invoiceNumber) {
  const key = invoiceKey(invoiceNumber);
  const row = await dbInvoice(db, userId, key);
  if (!row) throw new Error("Invoice not found");
  const inv = JSON.parse(row.data_json);
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
  const key = invoiceKey(number);
  const ts = nowIso();
  await db
    .prepare(
      `INSERT INTO doc_invoices (user_id, invoice_key, invoice_number, data_json, revision, updated_at, pdf_status)
       VALUES (?, ?, ?, ?, 1, ?, 'pending')
       ON CONFLICT(user_id, invoice_key) DO UPDATE SET
         data_json = excluded.data_json,
         invoice_number = excluded.invoice_number,
         revision = revision + 1,
         updated_at = excluded.updated_at`
    )
    .bind(userId, key, number, JSON.stringify(invoice), ts)
    .run();
  return key;
}

async function updateInvoiceStatus(db, userId, invoiceNumber, status) {
  const key = invoiceKey(invoiceNumber);
  const row = await db
    .prepare("SELECT data_json FROM doc_invoices WHERE user_id = ? AND invoice_key = ?")
    .bind(userId, key)
    .first();
  if (!row) return false;
  const inv = JSON.parse(row.data_json);
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
async function buildInvoicePdfBytes(invoice) {
  return buildInvoicePdf(invoice);
}

export async function generateInvoicePdf(env, userId, invoiceNumber) {
  const key = invoiceKey(invoiceNumber);
  const row = await dbInvoice(env.DB, userId, key);
  if (!row) throw new Error("Invoice not found");
  const invoice = JSON.parse(row.data_json);
  const bucket = documentsBucket(env);
  if (!bucket) throw new Error("Document storage not configured");
  const r2Key = pdfR2Key(userId, key);
  const bytes = await buildInvoicePdfBytes(invoice);
  await bucket.put(r2Key, bytes, {
    httpMetadata: { contentType: "application/pdf" },
  });
  const filename = `Invoice_${key}_${invoice.invoice_date || "draft"}.pdf`;
  invoice.filename = filename;
  invoice.pdf_status = "ready";
  const ts = nowIso();
  await env.DB.prepare(
    `UPDATE doc_invoices SET data_json = ?, pdf_status = 'ready', pdf_r2_key = ?, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
  )
    .bind(JSON.stringify(invoice), r2Key, ts, userId, key)
    .run();
  return { filename, r2Key };
}

async function dbInvoice(db, userId, key) {
  return db
    .prepare("SELECT * FROM doc_invoices WHERE user_id = ? AND invoice_key = ?")
    .bind(userId, key)
    .first();
}

export async function enqueueEmailSend(env, userId, invoiceNumber, userEmail) {
  const id = crypto.randomUUID();
  const ts = nowIso();
  await env.DB.prepare(
    `INSERT INTO email_outbox (id, user_id, invoice_number, status, created_at, updated_at)
     VALUES (?, ?, ?, 'pending', ?, ?)`
  )
    .bind(id, userId, invoiceNumber, ts, ts)
    .run();
  await updateInvoiceStatus(env.DB, userId, invoiceNumber, "send_queued");
  await processEmailOutbox(env, userId, userEmail);
  return { id, status: "send_queued" };
}

export async function processEmailOutbox(env, userId, userEmail) {
  const rows = await env.DB.prepare(
    `SELECT * FROM email_outbox WHERE user_id = ? AND status IN ('pending', 'generating_pdf', 'failed') ORDER BY created_at LIMIT 10`
  )
    .bind(userId)
    .all();
  const provider = env.EMAIL_PROVIDER || "log";
  for (const row of rows.results || []) {
    const ts = nowIso();
    try {
      const key = invoiceKey(row.invoice_number);
      let invRow = await dbInvoice(env.DB, userId, key);
      if (!invRow) continue;
      if (invRow.pdf_status !== "ready") {
        await env.DB.prepare(`UPDATE email_outbox SET status = 'generating_pdf', updated_at = ? WHERE id = ?`)
          .bind(ts, row.id)
          .run();
        await generateInvoicePdf(env, userId, row.invoice_number);
        invRow = await dbInvoice(env.DB, userId, key);
      }
      const invoice = JSON.parse(invRow.data_json);
      const custRow = await env.DB.prepare(
        "SELECT data_json FROM doc_customers WHERE user_id = ? AND name = ?"
      )
        .bind(userId, invoice.customer_name)
        .first();
      let customerEmail = "";
      if (custRow) {
        try {
          customerEmail = JSON.parse(custRow.data_json).email || "";
        } catch {
          /* ignore */
        }
      }
      if (!customerEmail && provider !== "log") {
        throw new Error("Customer email required");
      }
      const bucket = documentsBucket(env);
      const pdfObj = invRow.pdf_r2_key ? await bucket.get(invRow.pdf_r2_key) : null;
      const pdfBytes = pdfObj ? await pdfObj.arrayBuffer() : null;
      if (provider === "log") {
        console.log(
          JSON.stringify({
            action: "send_invoice_email",
            to: customerEmail || "(missing)",
            cc: userEmail,
            invoice_number: row.invoice_number,
            pdf_bytes: pdfBytes ? pdfBytes.byteLength : 0,
          })
        );
      } else if (env.RESEND_API_KEY && customerEmail) {
        const b64 = pdfBytes ? btoa(String.fromCharCode(...new Uint8Array(pdfBytes))) : "";
        await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.RESEND_API_KEY}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            from: env.EMAIL_FROM || "invoices@frogswork.com",
            to: [customerEmail],
            cc: userEmail ? [userEmail] : [],
            subject: `Invoice ${invoice.invoice_number} from FrogsWork`,
            text: `Please find your invoice attached.`,
            attachments: b64
              ? [{ filename: invoice.filename || "invoice.pdf", content: b64 }]
              : [],
          }),
        });
      }
      await env.DB.prepare(
        `UPDATE email_outbox SET status = 'sent', updated_at = ?, attempts = attempts + 1 WHERE id = ?`
      )
        .bind(ts, row.id)
        .run();
      await updateInvoiceStatus(env.DB, userId, row.invoice_number, "sent");
    } catch (exc) {
      await env.DB.prepare(
        `UPDATE email_outbox SET status = 'failed', last_error = ?, updated_at = ?, attempts = attempts + 1 WHERE id = ?`
      )
        .bind(String(exc.message || exc), ts, row.id)
        .run();
      await updateInvoiceStatus(env.DB, userId, row.invoice_number, "send_failed");
    }
  }
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
      await softDeleteInvoice(db, userId, payload.invoice_number);
      return { ok: true };
    case "create_invoice": {
      const key = await upsertInvoice(db, userId, payload.invoice);
      return { ok: true, invoice_key: key };
    }
    case "update_invoice_status":
      await updateInvoiceStatus(db, userId, payload.invoice_number, payload.status);
      return { ok: true };
    case "enqueue_email_send":
      return enqueueEmailSend(env, userId, payload.invoice_number, userEmail);
    default:
      return { ok: false, error: `Unknown mutation: ${type}` };
  }
}

export async function handleDocumentsRoute(request, env, path, auth, stripe) {
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
    for (const mutation of mutations) {
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

  const pdfMatch = path.match(/^\/documents\/invoices\/(\d+)\/pdf$/);
  if (pdfMatch && request.method === "GET") {
    const number = Number(pdfMatch[1]);
    const key = invoiceKey(number);
    let row = await dbInvoice(env.DB, userId, key);
    if (!row) return textError("Invoice not found", 404);
    if (row.pdf_status !== "ready") {
      await generateInvoicePdf(env, userId, number);
      row = await dbInvoice(env.DB, userId, key);
    }
    const bucket = documentsBucket(env);
    if (!row.pdf_r2_key || !bucket) return textError("PDF not available", 404);
    const obj = await bucket.get(row.pdf_r2_key);
    if (!obj) return textError("PDF not found", 404);
    const buf = await obj.arrayBuffer();
    const inv = JSON.parse(row.data_json);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    return json({ filename: inv.filename, content_b64: b64 });
  }

  const sendMatch = path.match(/^\/documents\/invoices\/(\d+)\/send$/);
  if (sendMatch && request.method === "POST") {
    const number = Number(sendMatch[1]);
    let body = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }
    if (body.pdf_b64) {
      const key = invoiceKey(number);
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
        await env.DB.prepare(
          `UPDATE doc_invoices SET pdf_status = 'ready', pdf_r2_key = ?, data_json = ?, updated_at = ? WHERE user_id = ? AND invoice_key = ?`
        )
          .bind(r2Key, JSON.stringify(inv), nowIso(), userId, key)
          .run();
      }
    }
    return enqueueEmailSend(env, userId, number, auth.user.email);
  }

  const genMatch = path.match(/^\/documents\/invoices\/(\d+)\/generate$/);
  if (genMatch && request.method === "POST") {
    const number = Number(genMatch[1]);
    const result = await generateInvoicePdf(env, userId, number);
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
      const inv = payload.invoice;
      const key = invoiceKey(inv.invoice_number);
      workspace.invoices[key] = { ...inv, pdf_status: inv.pdf_status || "pending" };
      return { ok: true, invoice_key: key };
    }
    case "update_invoice_status": {
      const key = invoiceKey(payload.invoice_number);
      if (workspace.invoices[key]) {
        workspace.invoices[key].status = payload.status;
      }
      return { ok: true };
    }
    case "upsert_settings":
      workspace.settings = { ...workspace.settings, ...(payload.settings || {}) };
      return { ok: true };
    case "delete_invoice": {
      const key = invoiceKey(payload.invoice_number);
      if (workspace.invoices[key]) {
        workspace.invoices[key].deleted_at = nowIso();
      }
      return { ok: true };
    }
    case "enqueue_email_send": {
      const key = invoiceKey(payload.invoice_number);
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

  const pdfMatch = path.match(/^\/documents\/invoices\/(\d+)\/pdf$/);
  if (pdfMatch && request.method === "GET") {
    const number = Number(pdfMatch[1]);
    const key = invoiceKey(number);
    const ws = await loadGuestWorkspace(env.DB, guestId);
    const inv = ws.invoices[key];
    if (!inv) return textError("Invoice not found", 404);
    const bytes = await buildInvoicePdfBytes(inv);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(bytes)));
    inv.pdf_status = "ready";
    ws.invoices[key] = inv;
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ filename: inv.filename || `Invoice_${key}.pdf`, content_b64: b64 });
  }

  const sendMatch = path.match(/^\/documents\/invoices\/(\d+)\/send$/);
  if (sendMatch && request.method === "POST") {
    const number = Number(sendMatch[1]);
    const ws = await loadGuestWorkspace(env.DB, guestId);
    const key = invoiceKey(number);
    if (!ws.invoices[key]) return textError("Invoice not found", 404);
    ws.invoices[key].status = "sent";
    ws.invoices[key].pdf_status = "ready";
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ ok: true, status: "sent", note: "Guest trial — upgrade to send real email." });
  }

  const genMatch = path.match(/^\/documents\/invoices\/(\d+)\/generate$/);
  if (genMatch && request.method === "POST") {
    const number = Number(genMatch[1]);
    const key = invoiceKey(number);
    const ws = await loadGuestWorkspace(env.DB, guestId);
    if (!ws.invoices[key]) return textError("Invoice not found", 404);
    const bytes = await buildInvoicePdfBytes(ws.invoices[key]);
    ws.invoices[key].pdf_status = "ready";
    await saveGuestWorkspace(env.DB, guestId, ws);
    return json({ ok: true, bytes: bytes.byteLength });
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
