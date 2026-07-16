import { decodePdfB64 } from "./upload_security.js";

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

export async function assertActiveSubscription(stripe, user, subscriptionStatus) {
  const sub = await subscriptionStatus(stripe, user.stripe_customer_id);
  if (!sub.active) {
    throw new Error("Active subscription required for automatic email send.");
  }
  return sub;
}

async function sendInvoiceViaResend(env, { to, cc, subject, text, filename, pdfBinary }) {
  if (!env.RESEND_API_KEY) {
    console.log(
      JSON.stringify({
        action: "relay_invoice_email",
        to,
        cc,
        subject,
        filename,
        pdf_bytes: pdfBinary?.byteLength || 0,
      })
    );
    return { ok: true, logged: true };
  }
  const u8 = pdfBinary instanceof Uint8Array ? pdfBinary : new Uint8Array(pdfBinary);
  const chunk = 0x8000;
  let binary = "";
  for (let i = 0; i < u8.length; i += chunk) {
    binary += String.fromCharCode(...u8.subarray(i, i + chunk));
  }
  const b64 = btoa(binary);
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM || "invoices@frogswork.com",
      to: [to],
      cc: cc ? [cc] : [],
      subject,
      text,
      attachments: [{ filename: filename || "invoice.pdf", content: b64 }],
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Resend error ${res.status}`);
  }
  return { ok: true };
}

/**
 * Local-tier relay: send invoice PDF from request body without persisting to D1/R2.
 * Requires authenticated user with active subscription.
 */
export async function handleInvoiceRelaySend(request, env, auth, { subscriptionStatus, getStripe }) {
  const sendMatch = new URL(request.url).pathname.match(/^\/email\/invoices\/(\d+)\/send$/);
  if (!sendMatch || request.method !== "POST") {
    return null;
  }

  let stripe;
  try {
    stripe = getStripe(env);
  } catch {
    return textError("Stripe is not configured.", 503);
  }

  try {
    await assertActiveSubscription(stripe, auth.user, subscriptionStatus);
  } catch (exc) {
    return textError(String(exc.message || exc), 403);
  }

  let body = {};
  try {
    body = await request.json();
  } catch {
    return textError("Invalid JSON body.", 400);
  }

  const invoiceNumber = Number(sendMatch[1]);
  const customerEmail = String(body.customer_email || "").trim();
  if (!customerEmail || !customerEmail.includes("@")) {
    return textError("customer_email is required.", 400);
  }
  if (!body.pdf_b64) {
    return textError("pdf_b64 is required for local send.", 400);
  }

  let pdfBinary;
  try {
    pdfBinary = decodePdfB64(body.pdf_b64);
  } catch (exc) {
    return textError(String(exc.message || exc), 400);
  }

  const filename =
    String(body.filename || "").trim() || `Invoice_${invoiceKey(invoiceNumber)}.pdf`;
  const subject =
    String(body.subject || "").trim() ||
    `Invoice #${invoiceKey(invoiceNumber)} from FrogsWork`;
  const text =
    String(body.body_text || "").trim() ||
    `Please find invoice #${invoiceKey(invoiceNumber)} attached.`;

  const userId = auth.user.id;
  const ts = nowIso();

  try {
    await sendInvoiceViaResend(env, {
      to: customerEmail,
      cc: auth.user.email,
      subject,
      text,
      filename,
      pdfBinary,
    });

    const id = crypto.randomUUID();
    await env.DB.prepare(
      `INSERT INTO email_outbox (id, user_id, invoice_number, status, created_at, updated_at)
       VALUES (?, ?, ?, 'sent', ?, ?)`
    )
      .bind(id, userId, invoiceNumber, ts, ts)
      .run();

    return json({ ok: true, status: "sent", id });
  } catch (exc) {
    const id = crypto.randomUUID();
    await env.DB.prepare(
      `INSERT INTO email_outbox (id, user_id, invoice_number, status, last_error, created_at, updated_at)
       VALUES (?, ?, ?, 'failed', ?, ?, ?)`
    )
      .bind(id, userId, invoiceNumber, String(exc.message || exc), ts, ts)
      .run();
    return textError(String(exc.message || exc), 502);
  }
}
