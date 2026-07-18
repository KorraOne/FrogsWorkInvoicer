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
    settings,
  };
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

  const invoicesForJson = {};
  for (const [key, inv] of Object.entries(snapshot.invoices)) {
    const { _pdf_r2_key, ...rest } = inv;
    invoicesForJson[key] = rest;
  }
  const exportJson = {
    exported_at: snapshot.exported_at,
    email: snapshot.email,
    businesses: snapshot.businesses,
    customers: snapshot.customers,
    invoices: invoicesForJson,
    settings: snapshot.settings,
    note: "This file is for your records. FrogsWork cannot restore it into your Cloud account.",
  };
  files.push({
    name: "frogswork-export.json",
    data: encoder.encode(JSON.stringify(exportJson, null, 2)),
  });

  const bucket = documentsBucket(env);
  let pdfCount = 0;
  let totalBytes = files[0].data.length;
  if (bucket) {
    for (const inv of Object.values(snapshot.invoices)) {
      const r2Key = inv._pdf_r2_key;
      if (!r2Key) continue;
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
      const num = inv.invoice_number != null ? String(inv.invoice_number) : inv.invoice_key;
      const safe = String(num).replace(/[^\w.-]+/g, "_");
      files.push({ name: `pdfs/${safe}.pdf`, data: buf });
      pdfCount += 1;
    }
  }

  const zip = buildZip(files);
  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(zip, {
    status: 200,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="frogswork-export-${stamp}.zip"`,
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
