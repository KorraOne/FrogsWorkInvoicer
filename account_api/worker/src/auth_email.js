import { sendTransactionalEmail } from "./mail.js";

const RESET_TTL_MS = 60 * 60 * 1000;
const VERIFY_TTL_MS = 7 * 24 * 60 * 60 * 1000;

function marketingBase(env, request) {
  const origin = request?.headers?.get("Origin") || "";
  if (origin.includes("127.0.0.1") || origin.includes("localhost")) {
    return origin.replace(/\/$/, "");
  }
  return (env.CHECKOUT_RETURN_BASE || "https://frogswork.com").replace(/\/$/, "");
}

async function hashToken(token) {
  const data = new TextEncoder().encode(token);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status) {
  return json({ error: message }, status);
}

export function isEmailVerified(user) {
  return Boolean(user?.email_verified_at);
}

export async function sendVerificationEmail(env, request, user) {
  const token = randomToken();
  const tokenHash = await hashToken(token);
  const now = new Date();
  const expiresAt = new Date(now.getTime() + VERIFY_TTL_MS).toISOString();
  await env.DB.prepare(
    `INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, created_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(user.id, tokenHash, expiresAt, now.toISOString())
    .run();

  const base = marketingBase(env, request);
  const link = `${base}/account/verify-email.html?token=${encodeURIComponent(token)}`;
  await sendTransactionalEmail(env, {
    to: user.email,
    subject: "Verify your FrogsWork email",
    text: `Verify your email for FrogsWork:\n\n${link}\n\nThis link expires in 7 days.`,
    html: `<p>Verify your email for FrogsWork:</p><p><a href="${link}">Verify email</a></p><p>This link expires in 7 days.</p>`,
  });
}

export async function handleForgotPassword(request, env, { userByEmail }) {
  const body = await request.json().catch(() => ({}));
  const email = (body.email || "").trim().toLowerCase();
  const generic = { ok: true, message: "If that email is registered, we sent reset instructions." };

  if (!email || !email.includes("@")) {
    return json(generic);
  }

  const user = await userByEmail(env.DB, email);
  if (!user) {
    return json(generic);
  }

  const token = randomToken();
  const tokenHash = await hashToken(token);
  const now = new Date();
  const expiresAt = new Date(now.getTime() + RESET_TTL_MS).toISOString();
  await env.DB.prepare(
    `INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(user.id, tokenHash, expiresAt, now.toISOString())
    .run();

  const base = marketingBase(env, request);
  const link = `${base}/account/reset-password.html?token=${encodeURIComponent(token)}`;
  try {
    await sendTransactionalEmail(env, {
      to: user.email,
      subject: "Reset your FrogsWork password",
      text: `Reset your FrogsWork password:\n\n${link}\n\nThis link expires in 1 hour. If you did not request this, ignore this email.`,
      html: `<p>Reset your FrogsWork password:</p><p><a href="${link}">Reset password</a></p><p>This link expires in 1 hour.</p>`,
    });
  } catch (exc) {
    console.error("forgot-password email failed:", exc);
  }
  return json(generic);
}

export async function handleResetPassword(request, env) {
  const body = await request.json().catch(() => ({}));
  const token = (body.token || "").trim();
  const password = body.password || "";
  if (!token) {
    return textError("Reset token is required.", 400);
  }
  if (!password || password.length < 8) {
    return textError("Password must be at least 8 characters.", 400);
  }

  const tokenHash = await hashToken(token);
  const row = await env.DB.prepare(
    `SELECT * FROM password_reset_tokens
     WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?`
  )
    .bind(tokenHash, new Date().toISOString())
    .first();
  if (!row) {
    return textError("Invalid or expired reset link.", 400);
  }

  const bcrypt = await import("bcryptjs");
  const passwordHash = bcrypt.hashSync(password, 10);
  const usedAt = new Date().toISOString();
  await env.DB.prepare("UPDATE users SET password_hash = ? WHERE id = ?")
    .bind(passwordHash, row.user_id)
    .run();
  await env.DB.prepare("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?")
    .bind(usedAt, row.id)
    .run();
  return json({ ok: true });
}

export async function handleVerifyEmail(request, env) {
  const body = await request.json().catch(() => ({}));
  const token = (body.token || "").trim();
  if (!token) {
    return textError("Verification token is required.", 400);
  }
  const tokenHash = await hashToken(token);
  const row = await env.DB.prepare(
    `SELECT * FROM email_verification_tokens
     WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?`
  )
    .bind(tokenHash, new Date().toISOString())
    .first();
  if (!row) {
    return textError("Invalid or expired verification link.", 400);
  }
  const usedAt = new Date().toISOString();
  await env.DB.prepare("UPDATE users SET email_verified_at = ? WHERE id = ?")
    .bind(usedAt, row.user_id)
    .run();
  await env.DB.prepare("UPDATE email_verification_tokens SET used_at = ? WHERE id = ?")
    .bind(usedAt, row.id)
    .run();
  return json({ ok: true, verified: true });
}

export async function handleResendVerification(request, env, { requireUser }) {
  const auth = await requireUser(request, env);
  if (auth.error) return auth.error;
  if (isEmailVerified(auth.user)) {
    return json({ ok: true, already_verified: true });
  }
  try {
    await sendVerificationEmail(env, request, auth.user);
  } catch (exc) {
    return textError(String(exc.message || exc), 503);
  }
  return json({ ok: true, sent: true });
}
