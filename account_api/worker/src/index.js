import Stripe from "stripe";
import bcrypt from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import {
  isValidInstallId,
  linkInstallOnRegister,
  recordEvent,
  updateSubscriptionMilestones,
  upsertHeartbeat,
} from "./telemetry.js";
import { buildAdminSummary, checkAdminAuth, renderAdminHtml } from "./admin.js";

const ACCESS_TTL_SEC = 12 * 60 * 60;
const REFRESH_TTL_SEC = 30 * 24 * 60 * 60;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status) {
  return json({ error: message }, status);
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

async function issueTokens(env, userId, email) {
  const secret = new TextEncoder().encode(env.JWT_SECRET);
  const now = Math.floor(Date.now() / 1000);
  const access = await new SignJWT({
    sub: String(userId),
    email,
    type: "access",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + ACCESS_TTL_SEC)
    .sign(secret);
  const refresh = await new SignJWT({
    sub: String(userId),
    email,
    type: "refresh",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + REFRESH_TTL_SEC)
    .sign(secret);
  return { access_token: access, refresh_token: refresh };
}

async function decodeToken(env, token, expectedType) {
  const secret = new TextEncoder().encode(env.JWT_SECRET);
  const { payload } = await jwtVerify(token, secret);
  if (payload.type !== expectedType) {
    throw new Error("wrong token type");
  }
  return payload;
}

async function userByEmail(db, email) {
  return db
    .prepare("SELECT * FROM users WHERE email = ?")
    .bind(email.toLowerCase())
    .first();
}

async function userById(db, userId) {
  return db.prepare("SELECT * FROM users WHERE id = ?").bind(userId).first();
}

function isoFromTimestamp(ts) {
  if (!ts) return null;
  return new Date(ts * 1000).toISOString();
}

function periodEndFromSubscription(sub) {
  let ts = sub.current_period_end || sub.cancel_at || null;
  const item = sub.items?.data?.[0];
  if (!ts && item?.current_period_end) {
    ts = item.current_period_end;
  }
  return isoFromTimestamp(ts);
}

function subscriptionIsCanceling(sub) {
  if (sub.cancel_at_period_end) return true;
  if (sub.cancel_at) return true;
  if (sub.canceled_at && (sub.status === "active" || sub.status === "trialing")) {
    return true;
  }
  return false;
}

function planIntervalFromSubscription(sub) {
  const item = sub.items?.data?.[0];
  return item?.price?.recurring?.interval || "";
}

async function subscriptionStatus(stripe, customerId) {
  if (!customerId) {
    return {
      active: false,
      status: "none",
      canceling: false,
      access_until: null,
      current_period_end: null,
      plan_interval: "",
    };
  }
  const subs = await stripe.subscriptions.list({
    customer: customerId,
    status: "all",
    limit: 5,
  });
  for (const sub of subs.data) {
    if (sub.status === "active" || sub.status === "trialing") {
      const accessUntil = periodEndFromSubscription(sub);
      return {
        active: true,
        status: sub.status,
        canceling: subscriptionIsCanceling(sub),
        access_until: accessUntil,
        current_period_end: accessUntil,
        plan_interval: planIntervalFromSubscription(sub),
      };
    }
  }
  for (const sub of subs.data) {
    if (sub.status === "canceled") {
      const ended = isoFromTimestamp(sub.ended_at);
      return {
        active: false,
        status: "canceled",
        canceling: false,
        access_until: ended,
        current_period_end: ended,
        plan_interval: planIntervalFromSubscription(sub),
      };
    }
  }
  return {
    active: false,
    status: "inactive",
    canceling: false,
    access_until: null,
    current_period_end: null,
    plan_interval: "",
  };
}

async function portalUrl(stripe, customerId) {
  if (!customerId) return null;
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: "https://frogswork.com/support.html",
  });
  return session.url;
}

async function requireUser(request, env) {
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Bearer ")) {
    return { error: textError("Unauthorized", 401) };
  }
  try {
    const payload = await decodeToken(env, header.slice(7), "access");
    const user = await userById(env.DB, Number(payload.sub));
    if (!user) {
      return { error: textError("Unauthorized", 401) };
    }
    return { user };
  } catch {
    return { error: textError("Invalid token", 401) };
  }
}

async function validatedCheckoutSession(stripe, sessionId) {
  const checkout = await stripe.checkout.sessions.retrieve(sessionId, {
    expand: ["subscription"],
  });
  if (checkout.payment_status !== "paid" && checkout.status !== "complete") {
    throw new Error("Checkout is not complete. Finish payment first.");
  }
  const email = (
    checkout.customer_details?.email ||
    checkout.customer_email ||
    ""
  )
    .trim()
    .toLowerCase();
  if (!email) {
    throw new Error("No email on this checkout session.");
  }
  let sub = checkout.subscription;
  if (typeof sub === "string") {
    sub = await stripe.subscriptions.retrieve(sub);
  }
  if (!sub || (sub.status !== "active" && sub.status !== "trialing")) {
    throw new Error("No active subscription on this checkout.");
  }
  let customerId = checkout.customer;
  if (typeof customerId === "object" && customerId?.id) {
    customerId = customerId.id;
  }
  return { email, customerId };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    const stripe = new Stripe(env.STRIPE_SECRET_KEY || "", {
      apiVersion: "2024-11-20.acacia",
    });

    if (path === "/health" && request.method === "GET") {
      return json({ ok: true, stripe: Boolean(env.STRIPE_SECRET_KEY) });
    }

    if (path === "/checkout/session-info" && request.method === "GET") {
      const sessionId = (url.searchParams.get("session_id") || "").trim();
      if (!sessionId.startsWith("cs_")) {
        return textError("Invalid checkout session.", 400);
      }
      try {
        const { email } = await validatedCheckoutSession(stripe, sessionId);
        const existing = await userByEmail(env.DB, email);
        return json({
          email,
          paid: true,
          subscription_active: true,
          account_exists: Boolean(existing),
        });
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
    }

    if (path === "/auth/register" && request.method === "POST") {
      const body = await readJson(request);
      const password = body.password || "";
      const sessionId = (body.checkout_session_id || "").trim();
      if (!password) {
        return textError("Password is required.", 400);
      }
      if (password.length < 8) {
        return textError("Password must be at least 8 characters.", 400);
      }
      if (!sessionId) {
        return textError("Checkout session is required to register.", 400);
      }

      let email;
      let customerId;
      try {
        ({ email, customerId } = await validatedCheckoutSession(stripe, sessionId));
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }

      if (await userByEmail(env.DB, email)) {
        return textError(
          "An account with this email is already registered. Try signing in.",
          409
        );
      }

      const passwordHash = bcrypt.hashSync(password, 10);
      const createdAt = new Date().toISOString();
      const result = await env.DB.prepare(
        "INSERT INTO users (email, password_hash, stripe_customer_id, created_at) VALUES (?, ?, ?, ?)"
      )
        .bind(email, passwordHash, customerId, createdAt)
        .run();

      const tokens = await issueTokens(env, result.meta.last_row_id, email);

      const installId = (body.install_id || "").trim().toLowerCase();
      if (isValidInstallId(installId)) {
        await linkInstallOnRegister(
          env.DB,
          installId,
          result.meta.last_row_id,
          body.signup_snapshot
        );
        const user = await userById(env.DB, result.meta.last_row_id);
        const sub = await subscriptionStatus(stripe, customerId);
        await updateSubscriptionMilestones(env.DB, user, sub);
      }

      return json({ ...tokens, email });
    }

    if (path === "/auth/attach-checkout" && request.method === "POST") {
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      const body = await readJson(request);
      const sessionId = (body.checkout_session_id || "").trim();
      if (!sessionId) {
        return textError("Checkout session is required.", 400);
      }
      let email;
      let customerId;
      try {
        ({ email, customerId } = await validatedCheckoutSession(stripe, sessionId));
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
      if (email !== auth.user.email.trim().toLowerCase()) {
        return textError("Checkout email does not match your account.", 400);
      }
      await env.DB.prepare(
        "UPDATE users SET stripe_customer_id = ? WHERE id = ?"
      )
        .bind(customerId, auth.user.id)
        .run();
      return json({ ok: true });
    }

    if (path === "/auth/login" && request.method === "POST") {
      const body = await readJson(request);
      const email = (body.email || "").trim().toLowerCase();
      const password = body.password || "";
      const user = await userByEmail(env.DB, email);
      if (!user || !bcrypt.compareSync(password, user.password_hash)) {
        return textError("Invalid email or password.", 401);
      }
      const tokens = await issueTokens(env, user.id, user.email);
      return json(tokens);
    }

    if (path === "/auth/refresh" && request.method === "POST") {
      const body = await readJson(request);
      const token = body.refresh_token || "";
      try {
        const payload = await decodeToken(env, token, "refresh");
        const user = await userById(env.DB, Number(payload.sub));
        if (!user) {
          return textError("Unauthorized", 401);
        }
        const tokens = await issueTokens(env, user.id, user.email);
        return json(tokens);
      } catch {
        return textError("Invalid refresh token.", 401);
      }
    }

    if (path === "/entitlements" && request.method === "GET") {
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      const sub = await subscriptionStatus(stripe, auth.user.stripe_customer_id);
      sub.portal_url = await portalUrl(stripe, auth.user.stripe_customer_id);
      await updateSubscriptionMilestones(env.DB, auth.user, sub);
      return json(sub);
    }

    if (path === "/telemetry/heartbeat" && request.method === "POST") {
      const body = await readJson(request);
      try {
        const result = await upsertHeartbeat(env.DB, body);
        return json({ ok: true, ...result });
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
    }

    if (path === "/telemetry/event" && request.method === "POST") {
      const body = await readJson(request);
      try {
        const result = await recordEvent(env.DB, body);
        return json({ ok: true, ...result });
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
    }

    if (path === "/admin/api/summary" && request.method === "GET") {
      const auth = checkAdminAuth(request, env.ADMIN_PASSWORD);
      if (!auth.ok) return auth.response;
      const summary = await buildAdminSummary(env.DB);
      return json(summary);
    }

    if (path === "/admin" && request.method === "GET") {
      const auth = checkAdminAuth(request, env.ADMIN_PASSWORD);
      if (!auth.ok) return auth.response;
      const summary = await buildAdminSummary(env.DB);
      return new Response(renderAdminHtml(summary), {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    if (path === "/releases/latest" && request.method === "GET") {
      if (!env.CLIENT_RELEASE_VERSION) {
        return new Response("", { status: 204 });
      }
      return json({
        version: env.CLIENT_RELEASE_VERSION,
        download_url: env.CLIENT_RELEASE_URL || "",
        sha256: env.CLIENT_RELEASE_SHA256 || "",
        notes: env.CLIENT_RELEASE_NOTES || "",
      });
    }

    if (path === "/webhooks/stripe" && request.method === "POST") {
      // Ack only — GET /entitlements queries Stripe live; no DB cache yet.
      if (!env.STRIPE_WEBHOOK_SECRET) {
        return textError("Webhook secret not configured.", 500);
      }
      const payload = await request.text();
      const sig = request.headers.get("Stripe-Signature") || "";
      try {
        stripe.webhooks.constructEvent(payload, sig, env.STRIPE_WEBHOOK_SECRET);
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
      return json({ received: true });
    }

    return textError("Not found", 404);
  },
};
