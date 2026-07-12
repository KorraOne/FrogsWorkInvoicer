export async function sendTransactionalEmail(env, { to, subject, text, html }) {
  if (!env.RESEND_API_KEY) {
    console.log(
      JSON.stringify({
        action: "transactional_email",
        to,
        subject,
        preview: (text || "").slice(0, 120),
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
      text,
      html: html || undefined,
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Resend error ${res.status}`);
  }
  return { ok: true };
}
