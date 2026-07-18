/**
 * One-time cross-domain auth handoff (frogswork.com → app.frogswork.com).
 * Codes are opaque, single-use, ~60s TTL; only SHA-256 hashes are stored.
 */

import { decodeSignupToken } from "./billing.js";

const HANDOFF_TTL_SEC = 60;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status = 400) {
  return json({ error: message }, status);
}

async function sha256Hex(value) {
  const data = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomCode() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function resolveBearerUser(request, env, { requireUser, userById }) {
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Bearer ")) {
    return { error: textError("Unauthorized", 401) };
  }
  const token = header.slice(7);
  try {
    const payload = await decodeSignupToken(env, token);
    const user = await userById(env.DB, Number(payload.sub));
    if (!user) return { error: textError("Unauthorized", 401) };
    if (user.email !== (payload.email || "").trim().toLowerCase()) {
      return { error: textError("Unauthorized", 401) };
    }
    return { user };
  } catch {
    /* try access token */
  }
  const auth = await requireUser(request, env);
  if (auth.error) return auth;
  return { user: auth.user };
}

async function userIsEntitled(env, user, subscriptionStatus, getStripe) {
  const status = (user.account_status || "active").trim();
  if (status === "pending_payment") return false;
  if (status === "active" && user.stripe_customer_id) {
    try {
      const stripe = getStripe(env);
      const sub = await subscriptionStatus(stripe, user.stripe_customer_id);
      return Boolean(sub.active);
    } catch {
      return status === "active";
    }
  }
  return status === "active";
}

export async function cleanupExpiredHandoffCodes(db) {
  const now = new Date().toISOString();
  const result = await db
    .prepare("DELETE FROM auth_handoff_codes WHERE expires_at < ? OR used_at IS NOT NULL")
    .bind(now)
    .run();
  return result?.meta?.changes || 0;
}

/**
 * POST /auth/handoff/create — Bearer access or signup token.
 * Returns { code } (plaintext, single-use, 60s).
 */
export async function handleHandoffCreate(request, env, deps) {
  const auth = await resolveBearerUser(request, env, deps);
  if (auth.error) return auth.error;

  const entitled = await userIsEntitled(
    env,
    auth.user,
    deps.subscriptionStatus,
    deps.getStripe
  );
  if (!entitled) {
    return textError("An active subscription is required.", 403);
  }

  const code = randomCode();
  const codeHash = await sha256Hex(code);
  const now = new Date();
  const expiresAt = new Date(now.getTime() + HANDOFF_TTL_SEC * 1000).toISOString();
  const createdAt = now.toISOString();

  await env.DB.prepare(
    `INSERT INTO auth_handoff_codes (code_hash, user_id, expires_at, created_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(codeHash, auth.user.id, expiresAt, createdAt)
    .run();

  return json({ code, expires_in: HANDOFF_TTL_SEC });
}

/**
 * POST /auth/handoff/redeem — body { code }. Issues fresh tokens.
 */
export async function handleHandoffRedeem(request, env, deps) {
  const body = await request.json().catch(() => ({}));
  const code = String(body.code || "").trim();
  if (!code || code.length < 32 || code.length > 128) {
    return textError("Invalid handoff code.", 400);
  }

  const codeHash = await sha256Hex(code);
  const now = new Date().toISOString();

  const updated = await env.DB.prepare(
    `UPDATE auth_handoff_codes
     SET used_at = ?
     WHERE code_hash = ? AND used_at IS NULL AND expires_at > ?
     RETURNING user_id`
  )
    .bind(now, codeHash, now)
    .first();

  if (!updated?.user_id) {
    return textError("Handoff code is invalid or expired.", 401);
  }

  const user = await deps.userById(env.DB, Number(updated.user_id));
  if (!user) {
    return textError("Unauthorized", 401);
  }

  const entitled = await userIsEntitled(
    env,
    user,
    deps.subscriptionStatus,
    deps.getStripe
  );
  if (!entitled) {
    return textError("An active subscription is required.", 403);
  }

  const tokens = await deps.issueTokens(env, user.id, user.email);
  return json(tokens);
}
