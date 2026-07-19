import { appendBrandedFooter } from "./email_branding.js";

export async function sendTransactionalEmail(
  env,
  { to, subject, text, html, skipBranding = false }
) {
  let bodyText = text;
  let bodyHtml = html;
  if (!skipBranding) {
    const branded = appendBrandedFooter(text, html, { variant: "transactional" });
    bodyText = branded.text;
    bodyHtml = branded.html;
  }
  if (!env.RESEND_API_KEY) {
    console.log(
      JSON.stringify({
        action: "transactional_email",
        to,
        subject,
        preview: (bodyText || "").slice(0, 120),
      })
    );
    return { ok: true, logged: true };
  }
  const from = env.EMAIL_FROM || "noreply@frogswork.com";
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from,
      to: Array.isArray(to) ? to : [to],
      subject,
      text: bodyText,
      html: bodyHtml || undefined,
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Resend error ${res.status}`);
  }
  return { ok: true };
}
