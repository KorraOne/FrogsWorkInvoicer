/**
 * Account export, wipe cloud data, and delete account.
 * Deletion is permanent — no restore/reseed path.
 */

const MAX_EXPORT_PDFS = 400;
const MAX_EXPORT_BYTES = 40 * 1024 * 1024;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status = 400) {
  return json({ error: message }, status);
}

function documentsBucket(env) {
  return env.DOCUMENTS;
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

/** CRC32 for ZIP (IEEE). */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u16(n) {
  const b = new Uint8Array(2);
  new DataView(b.buffer).setUint16(0, n, true);
  return b;
}

function u32(n) {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n >>> 0, true);
  return b;
}

function concatBytes(parts) {
  let len = 0;
  for (const p of parts) len += p.length;
  const out = new Uint8Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

/** Store-method ZIP (no compression). */
function buildZip(files) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const data = file.data instanceof Uint8Array ? file.data : new Uint8Array(file.data);
    const crc = crc32(data);
    const localHeader = concatBytes([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
    ]);
    localParts.push(localHeader, data);

    const central = concatBytes([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ]);
    centralParts.push(central);
    offset += localHeader.length + data.length;
  }

  const centralDir = concatBytes(centralParts);
  const end = concatBytes([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDir.length),
    u32(offset),
    u16(0),
  ]);
  return concatBytes([...localParts, centralDir, end]);
}

export async function purgeUserCloudData(env, userId) {
  const db = env.DB;
  const counts = {};
  for (const [label, sql] of [
    ["doc_invoices", "DELETE FROM doc_invoices WHERE user_id = ?"],
    ["doc_quotes", "DELETE FROM doc_quotes WHERE user_id = ?"],
    ["doc_businesses", "DELETE FROM doc_businesses WHERE user_id = ?"],
    ["doc_customers", "DELETE FROM doc_customers WHERE user_id = ?"],
    ["doc_settings", "DELETE FROM doc_settings WHERE user_id = ?"],
    ["email_outbox", "DELETE FROM email_outbox WHERE user_id = ?"],
    ["account_devices", "DELETE FROM account_devices WHERE user_id = ?"],
    ["auth_handoff_codes", "DELETE FROM auth_handoff_codes WHERE user_id = ?"],
    ["password_reset_tokens", "DELETE FROM password_reset_tokens WHERE user_id = ?"],
    ["email_verification_tokens", "DELETE FROM email_verification_tokens WHERE user_id = ?"],
  ]) {
    try {
      const res = await db.prepare(sql).bind(userId).run();
      counts[label] = res.meta?.changes ?? 0;
    } catch {
      counts[label] = 0;
    }
  }
  const bucket = documentsBucket(env);
  counts.r2_deleted = await deleteR2Prefix(bucket, `user-docs/${userId}/`);
  return counts;
}

async function loadExportSnapshot(db, user) {
  const userId = user.id;
  const businesses = {};
  const bizRows = await db
    .prepare("SELECT name, data_json FROM doc_businesses WHERE user_id = ?")
    .bind(userId)
    .all();
  for (const row of bizRows.results || []) {
    try {
      businesses[row.name] = JSON.parse(row.data_json || "{}");
    } catch {
      businesses[row.name] = {};
    }
  }

  const customers = {};
  const custRows = await db
    .prepare("SELECT name, data_json FROM doc_customers WHERE user_id = ?")
    .bind(userId)
    .all();
  for (const row of custRows.results || []) {
    try {
      customers[row.name] = JSON.parse(row.data_json || "{}");
    } catch {
      customers[row.name] = {};
    }
  }

  const invoices = {};
  const invRows = await db
    .prepare(
      "SELECT invoice_key, invoice_number, data_json, pdf_status, pdf_r2_key FROM doc_invoices WHERE user_id = ?"
    )
    .bind(userId)
    .all();
  for (const row of invRows.results || []) {
    let data = {};
    try {
      data = JSON.parse(row.data_json || "{}");
    } catch {
      data = {};
    }
    invoices[row.invoice_key] = {
      ...data,
      invoice_key: row.invoice_key,
      invoice_number: row.invoice_number,
      pdf_status: row.pdf_status || null,
      _pdf_r2_key: row.pdf_r2_key || null,
    };
  }

  const quotes = {};
  try {
    const quoteRows = await db
      .prepare(
        "SELECT quote_key, quote_number, data_json, pdf_status, pdf_r2_key FROM doc_quotes WHERE user_id = ?"
      )
      .bind(userId)
      .all();
    for (const row of quoteRows.results || []) {
      let data = {};
      try {
        data = JSON.parse(row.data_json || "{}");
      } catch {
        data = {};
      }
      quotes[row.quote_key] = {
        ...data,
        quote_key: row.quote_key,
        quote_number: row.quote_number,
        pdf_status: row.pdf_status || null,
        _pdf_r2_key: row.pdf_r2_key || null,
      };
    }
  } catch {
    /* table may not exist yet */
  }

  let settings = {};
  const settingsRow = await db
    .prepare("SELECT data_json FROM doc_settings WHERE user_id = ?")
    .bind(userId)
    .first();
  if (settingsRow?.data_json) {
    try {
      settings = JSON.parse(settingsRow.data_json);
    } catch {
      settings = {};
    }
  }

  return {
    exported_at: new Date().toISOString(),
    email: user.email,
    businesses,
    customers,
    invoices,
    quotes,
    settings,
  };
}

function invoiceExportBucket(inv) {
  if (inv.deleted_at) return "_deleted";
  const status = String(inv.status || "not_sent").toLowerCase();
  if (status === "paid") return "paid";
  if (status === "sent") return "sent_not_paid";
  return "not_sent";
}

function quoteExportBucket(quote) {
  if (quote.deleted_at) return "_deleted";
  const status = String(quote.status || "not_sent").toLowerCase();
  if (status === "sent") return "sent";
  if (status === "closed") return "closed";
  if (status === "converted") return "converted";
  return "not_sent";
}

function safeExportBaseName(prefix, number, date, key) {
  const num = number != null ? String(number) : "unknown";
  const datePart = String(date || "nodate").slice(0, 10).replace(/[^\w.-]+/g, "_");
  const keySuffix = String(key || "")
    .replace(/[^\w.-]+/g, "_")
    .slice(0, 12);
  const safeNum = num.replace(/[^\w.-]+/g, "_");
  return `${prefix}_${safeNum}_${datePart}_${keySuffix}`;
}

function stripPdfKey(doc) {
  const { _pdf_r2_key, ...rest } = doc;
  return rest;
}

async function cancelStripeSubscriptions(stripe, customerId) {
  if (!customerId || !stripe) return { cancelled: 0 };
  const subs = await stripe.subscriptions.list({
    customer: customerId,
    status: "all",
    limit: 20,
  });
  let cancelled = 0;
  for (const sub of subs.data || []) {
    if (sub.status === "active" || sub.status === "trialing" || sub.status === "past_due") {
      await stripe.subscriptions.cancel(sub.id);
      cancelled += 1;
    }
  }
  return { cancelled };
}

/**
 * GET /account/export
 */
export async function handleAccountExport(request, env, auth) {
  const snapshot = await loadExportSnapshot(env.DB, auth.user);
  const files = [];
  const encoder = new TextEncoder();
  const stamp = new Date().toISOString().slice(0, 10);
  const root = `frogswork_data_export_${stamp}`;

  const readme = [
    "FrogsWork Cloud data export",
    "",
    "This archive is for your records. It cannot be re-imported into FrogsWork.",
    "",
    "account.json       — account email / export metadata",
    "businesses.json    — business profiles",
    "customers.json     — customers",
    "settings.json      — app settings",
    "invoices/          — invoices grouped by status",
    "  not_sent/        — draft / send_queued / send_failed",
    "  sent_not_paid/   — sent, awaiting payment",
    "  paid/            — paid",
    "  _deleted/        — soft-deleted invoices",
    "quotes/            — quotes / price estimates grouped by status",
    "  not_sent/        — draft / send_queued / send_failed",
    "  sent/            — sent, awaiting reply",
    "  closed/          — closed (not accepted)",
    "  converted/       — converted to an invoice (see converted_invoice_id)",
    "  _deleted/        — soft-deleted quotes",
    "",
    "Each document folder contains paired .json and .pdf files when a PDF was stored.",
  ].join("\n");

  files.push({ name: `${root}/README.txt`, data: encoder.encode(readme) });
  files.push({
    name: `${root}/account.json`,
    data: encoder.encode(
      JSON.stringify(
        {
          exported_at: snapshot.exported_at,
          email: snapshot.email,
          note: "This archive is for your records. FrogsWork cannot restore it into your Cloud account.",
        },
        null,
        2
      )
    ),
  });
  files.push({
    name: `${root}/businesses.json`,
    data: encoder.encode(JSON.stringify(snapshot.businesses, null, 2)),
  });
  files.push({
    name: `${root}/customers.json`,
    data: encoder.encode(JSON.stringify(snapshot.customers, null, 2)),
  });
  files.push({
    name: `${root}/settings.json`,
    data: encoder.encode(JSON.stringify(snapshot.settings, null, 2)),
  });

  const bucket = documentsBucket(env);
  let pdfCount = 0;
  let totalBytes = files.reduce((n, f) => n + f.data.length, 0);

  async function addDocPair(folderKind, bucketName, baseName, doc) {
    const jsonBytes = encoder.encode(JSON.stringify(stripPdfKey(doc), null, 2));
    totalBytes += jsonBytes.length;
    if (totalBytes > MAX_EXPORT_BYTES) {
      throw new Error("EXPORT_TOO_LARGE");
    }
    files.push({
      name: `${root}/${folderKind}/${bucketName}/${baseName}.json`,
      data: jsonBytes,
    });

    const r2Key = doc._pdf_r2_key;
    if (!r2Key || !bucket) return;
    if (pdfCount >= MAX_EXPORT_PDFS) {
      throw new Error("EXPORT_TOO_MANY_PDFS");
    }
    const obj = await bucket.get(r2Key);
    if (!obj) return;
    const buf = new Uint8Array(await obj.arrayBuffer());
    totalBytes += buf.length;
    if (totalBytes > MAX_EXPORT_BYTES) {
      throw new Error("EXPORT_TOO_LARGE");
    }
    files.push({
      name: `${root}/${folderKind}/${bucketName}/${baseName}.pdf`,
      data: buf,
    });
    pdfCount += 1;
  }

  try {
    for (const [key, inv] of Object.entries(snapshot.invoices)) {
      const folder = invoiceExportBucket(inv);
      const base = safeExportBaseName(
        "Invoice",
        inv.invoice_number,
        inv.invoice_date,
        key
      );
      await addDocPair("invoices", folder, base, inv);
    }
    for (const [key, quote] of Object.entries(snapshot.quotes || {})) {
      const folder = quoteExportBucket(quote);
      const base = safeExportBaseName(
        "Quote",
        quote.quote_number,
        quote.quote_date || quote.invoice_date,
        key
      );
      await addDocPair("quotes", folder, base, quote);
    }
  } catch (exc) {
    if (String(exc.message) === "EXPORT_TOO_MANY_PDFS") {
      return textError(
        "Export is too large (too many PDFs). Contact support if you need a full archive.",
        413
      );
    }
    if (String(exc.message) === "EXPORT_TOO_LARGE") {
      return textError(
        "Export is too large. Contact support if you need a full archive.",
        413
      );
    }
    throw exc;
  }

  const zip = buildZip(files);
  return new Response(zip, {
    status: 200,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="frogswork-export-${stamp}.zip"`,
      "Cache-Control": "no-store",
    },
  });
}

/** Parse AU financial year token like 2025-26 → 1 Jul 2025 .. 30 Jun 2026. */
export function parseAuFinancialYear(fyRaw, today = new Date()) {
  let raw = String(fyRaw || "").trim();
  if (!raw) {
    const y = today.getUTCFullYear();
    const m = today.getUTCMonth() + 1; // 1-12
    const startYear = m >= 7 ? y : y - 1;
    raw = `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
  }
  const m = raw.match(/^(\d{4})[-/](\d{2})$/);
  if (!m) return null;
  const startYear = Number(m[1]);
  const endYy = Number(m[2]);
  const expectedEnd = (startYear + 1) % 100;
  if (!Number.isFinite(startYear) || endYy !== expectedEnd) return null;
  const endYear = startYear + 1;
  return {
    token: `${startYear}-${String(endYy).padStart(2, "0")}`,
    start: `${startYear}-07-01`,
    end: `${endYear}-06-30`,
    display: `${startYear}–${String(endYear).slice(2)}`,
    slug: `FY${String(startYear).slice(2)}${String(endYear).slice(2)}`,
    fileSlug: `FY${String(startYear).slice(2)}_${String(endYear).slice(2)}`,
  };
}

function isoInRange(iso, start, end) {
  const d = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false;
  return d >= start && d <= end;
}

function padInvoiceNum(n) {
  return String(Math.max(0, parseInt(String(n), 10) || 0)).padStart(8, "0");
}

function formatAuDate(iso) {
  const d = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return "";
  return `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;
}

function formatMoneyCsv(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "0.00";
  return v.toFixed(2);
}

function csvEscape(value) {
  const s = String(value ?? "");
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function sanitizeFilenamePart(raw, maxLen = 40) {
  return String(raw || "unknown")
    .replace(/[^\w.\-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, maxLen) || "unknown";
}

function includeInvoiceForTaxExport(inv, fy, businessFilter) {
  if (inv?.deleted_at) return false;
  if (businessFilter && String(inv.business_name || "") !== businessFilter) return false;
  const status = String(inv.status || "not_sent");
  if (status === "paid") {
    if (inv.paid_date && isoInRange(inv.paid_date, fy.start, fy.end)) return true;
    // Legacy Cloud invoices marked paid before paid_date was persisted.
    if (!inv.paid_date && isoInRange(inv.invoice_date, fy.start, fy.end)) return true;
    return false;
  }
  if (["not_sent", "send_queued", "send_failed", "sent"].includes(status)) {
    return isoInRange(inv.invoice_date, fy.start, fy.end);
  }
  return false;
}

/**
 * GET /account/tax-export?fy=2025-26&business=OptionalName
 */
export async function handleAccountTaxExport(request, env, auth) {
  const url = new URL(request.url);
  const fy = parseAuFinancialYear(url.searchParams.get("fy") || "");
  if (!fy) {
    return textError("Invalid financial year. Use e.g. fy=2025-26.", 400);
  }
  const businessFilter = String(url.searchParams.get("business") || "").trim();

  const snapshot = await loadExportSnapshot(env.DB, auth.user);
  const businesses = snapshot.businesses || {};
  if (businessFilter && !businesses[businessFilter]) {
    return textError("Business not found.", 404);
  }

  const rows = [];
  for (const [key, inv] of Object.entries(snapshot.invoices || {})) {
    if (!includeInvoiceForTaxExport(inv, fy, businessFilter || "")) continue;
    rows.push({ key, inv });
  }
  rows.sort((a, b) => {
    const da = String(a.inv.invoice_date || "");
    const db = String(b.inv.invoice_date || "");
    if (da !== db) return da.localeCompare(db);
    return Number(a.inv.invoice_number || 0) - Number(b.inv.invoice_number || 0);
  });

  const multiBiz = Object.keys(businesses).length > 1;
  const stamp = new Date().toISOString().slice(0, 10);
  const root = `frogswork_tax_export_${fy.fileSlug}_${stamp}`;
  const encoder = new TextEncoder();
  const files = [];

  const bizNames = businessFilter
    ? [businessFilter]
    : [...new Set(rows.map((r) => String(r.inv.business_name || "").trim()).filter(Boolean))];
  const bizLines = (bizNames.length ? bizNames : Object.keys(businesses)).map((name) => {
    const b = businesses[name] || {};
    const abn = String(b.business_abn || b.abn || "").trim();
    return abn ? `${name} (ABN ${abn})` : name || "(unnamed business)";
  });

  const header = [
    "Invoice Date",
    "Invoice Number",
    "Business Name",
    "Customer Name",
    "Customer ABN",
    "Gross Amount (Inc. GST)",
    "GST Amount",
    "Net Amount (Ex. GST)",
    "Status",
    "Date Paid",
  ];
  const csvLines = [header.map(csvEscape).join(",")];
  let totalEx = 0;
  let totalGst = 0;
  let totalInc = 0;
  let paidCount = 0;
  let unpaidCount = 0;

  for (const { inv } of rows) {
    const status = String(inv.status || "") === "paid" ? "Paid" : "Unpaid";
    if (status === "Paid") paidCount += 1;
    else unpaidCount += 1;
    const ex = Number(inv.amount_ex_gst || 0) || 0;
    const gst = Number(inv.gst_amount || 0) || 0;
    const inc = Number(inv.total_inc_gst || 0) || 0;
    totalEx += ex;
    totalGst += gst;
    totalInc += inc;
    csvLines.push(
      [
        formatAuDate(inv.invoice_date),
        padInvoiceNum(inv.invoice_number),
        inv.business_name || "",
        inv.customer_name || "",
        inv.customer_abn || "",
        formatMoneyCsv(inc),
        formatMoneyCsv(gst),
        formatMoneyCsv(ex),
        status,
        formatAuDate(inv.paid_date),
      ]
        .map(csvEscape)
        .join(",")
    );
  }

  const ledgerName = `income_ledger_${fy.fileSlug}.csv`;
  files.push({
    name: `${root}/${ledgerName}`,
    data: encoder.encode(csvLines.join("\r\n") + "\r\n"),
  });

  const readme = [
    "FrogsWork tax-time export",
    "",
    `Business: ${bizLines.join("; ") || "(none)"}`,
    `Financial year: ${fy.display} (${formatAuDate(fy.start)} to ${formatAuDate(fy.end)})`,
    `Generated: ${stamp}`,
    "",
    "Generated via FrogsWork Invoicing. This package contains a complete income ledger and matching PDF tax invoices.",
    "",
    `${ledgerName}     — income ledger (importable CSV; no totals in the data rows)`,
    "summary.txt               — totals and counts for a quick check",
    "invoice_pdfs/             — tax invoice PDFs for the ledger rows (when available)",
    "",
    "Inclusion: paid invoices by payment date in the FY (cash basis), plus unpaid invoices",
    "dated in the FY. Quotes and soft-deleted invoices are not included.",
  ].join("\n");
  files.push({ name: `${root}/README.txt`, data: encoder.encode(readme) });

  const summary = [
    "FrogsWork tax-time summary",
    "",
    `Financial year: ${fy.display}`,
    `Date range: ${formatAuDate(fy.start)} to ${formatAuDate(fy.end)}`,
    `Business: ${bizLines.join("; ") || "(none)"}`,
    "",
    `Invoice rows: ${rows.length} (${paidCount} paid, ${unpaidCount} unpaid)`,
    `Total Revenue (Ex. GST): $${formatMoneyCsv(totalEx)}`,
    `Total GST Collected: $${formatMoneyCsv(totalGst)}`,
    `Total Gross Revenue: $${formatMoneyCsv(totalInc)}`,
  ].join("\n");
  files.push({ name: `${root}/summary.txt`, data: encoder.encode(summary) });

  const bucket = documentsBucket(env);
  let pdfCount = 0;
  let totalBytes = files.reduce((n, f) => n + f.data.length, 0);

  for (const { key, inv } of rows) {
    const r2Key = inv._pdf_r2_key;
    if (!r2Key || !bucket) continue;
    if (pdfCount >= MAX_EXPORT_PDFS) {
      return textError(
        "Export is too large (too many PDFs). Contact support if you need a full archive.",
        413
      );
    }
    const obj = await bucket.get(r2Key);
    if (!obj) continue;
    const buf = new Uint8Array(await obj.arrayBuffer());
    totalBytes += buf.length;
    if (totalBytes > MAX_EXPORT_BYTES) {
      return textError(
        "Export is too large. Contact support if you need a full archive.",
        413
      );
    }
    const datePart = String(inv.invoice_date || "nodate").slice(0, 10).replace(/-/g, "") || "nodate";
    const numPart = padInvoiceNum(inv.invoice_number);
    const custPart = sanitizeFilenamePart(inv.customer_name);
    const bizPart = multiBiz ? `_${sanitizeFilenamePart(inv.business_name, 24)}` : "";
    const pdfName = `${datePart}_${numPart}_${custPart}${bizPart}.pdf`;
    files.push({
      name: `${root}/invoice_pdfs/${pdfName}`,
      data: buf,
    });
    pdfCount += 1;
  }

  const zip = buildZip(files);
  return new Response(zip, {
    status: 200,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="frogswork-tax-export-${fy.fileSlug}-${stamp}.zip"`,
      "Cache-Control": "no-store",
    },
  });
}

/**
 * POST /account/data/delete  body: { confirm: "DELETE DATA" }
 */
export async function handleAccountDataDelete(request, env, auth) {
  const body = await request.json().catch(() => ({}));
  if (String(body.confirm || "").trim() !== "DELETE DATA") {
    return textError('Type DELETE DATA exactly to confirm.', 400);
  }
  const counts = await purgeUserCloudData(env, auth.user.id);
  return json({ ok: true, counts });
}

/**
 * POST /account/delete  body: { confirm: "DELETE ACCOUNT", password }
 */
export async function handleAccountDelete(request, env, auth, deps) {
  const body = await request.json().catch(() => ({}));
  if (String(body.confirm || "").trim() !== "DELETE ACCOUNT") {
    return textError("Type DELETE ACCOUNT exactly to confirm.", 400);
  }
  const password = body.password || "";
  if (!password) {
    return textError("Password is required.", 400);
  }
  const { bcrypt, getStripe } = deps;
  if (!bcrypt.compareSync(password, auth.user.password_hash)) {
    return textError("Wrong password.", 401);
  }

  let stripeCancel = { cancelled: 0 };
  try {
    const stripe = getStripe(env);
    stripeCancel = await cancelStripeSubscriptions(stripe, auth.user.stripe_customer_id);
  } catch (exc) {
    console.error("account delete stripe cancel:", exc);
  }

  const counts = await purgeUserCloudData(env, auth.user.id);
  await env.DB.prepare("UPDATE installs SET user_id = NULL WHERE user_id = ?")
    .bind(auth.user.id)
    .run();
  await env.DB.prepare("DELETE FROM users WHERE id = ?").bind(auth.user.id).run();

  return json({ ok: true, stripe: stripeCancel, counts });
}
