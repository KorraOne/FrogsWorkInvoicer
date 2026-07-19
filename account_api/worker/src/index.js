import Stripe from "stripe";
import { jwtSecretBytes } from "./jwt_secret.js";
import bcrypt from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import {
  isValidInstallId,
  linkInstallOnRegister,
  recordEvent,
  updateSubscriptionMilestones,
  upsertHeartbeat,
} from "./telemetry.js";
import {
  resolveStorageTier,
  storageTierFromSubscription,
  entitlementsPlatforms,
  handleDocumentsRoute,
  handleGuestDocumentsRoute,
  handleGuestRoute,
  processEmailOutbox,
  processPaymentFollowups,
  verifyGuestToken,
} from "./documents.js";
import { corsPreflight, withCors } from "./cors.js";
import {
  handleSignup,
  handleCreateCheckoutSession,
  handleCheckoutSessionInfo,
  handleStripeWebhook,
  cleanupPendingUsers,
  activateUserFromCheckout,
} from "./billing.js";
import {
  handleForgotPassword,
  handleResetPassword,
  handleVerifyEmail,
  handleResendVerification,
  isEmailVerified,
} from "./auth_email.js";
import { checkRateLimit, clientIp, rateLimitResponse } from "./rate_limit.js";
import { handleInvoiceRelaySend } from "./invoice_relay.js";
import { handleMobileRoute } from "./mobile.js";
import { purgeAndSeedFromStripe } from "./dev_seed.js";
import { buildMetricsSummary, checkMetricsAuth } from "./metrics.js";
import { upsertAccountDevice } from "./devices.js";
import {
  handleHandoffCreate,
  handleHandoffRedeem,
  cleanupExpiredHandoffCodes,
} from "./handoff.js";
import {
  handleAccountExport,
  handleAccountTaxExport,
  handleAccountDataDelete,
  handleAccountDelete,
} from "./account_lifecycle.js";

const ACCESS_TTL_SEC = 12 * 60 * 60;
const REFRESH_TTL_SEC = 30 * 24 * 60 * 60;
const STRIPE_API_VERSION = "2024-11-20.acacia";

function getStripe(env) {
  const key = env.STRIPE_SECRET_KEY;
  if (!key) {
    throw new Error("Stripe is not configured.");
  }
  return new Stripe(key, { apiVersion: STRIPE_API_VERSION });
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

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

async function issueTokens(env, userId, email) {
  const secret = jwtSecretBytes(env);
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
  const secret = jwtSecretBytes(env);
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

async function requireUserOrGuest(request, env) {
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Bearer ")) {
    return { error: textError("Unauthorized", 401) };
  }
  const token = header.slice(7);
  try {
    const payload = await decodeToken(env, token, "access");
    const user = await userById(env.DB, Number(payload.sub));
    if (user) {
      return { kind: "user", user };
    }
  } catch {
    /* try guest */
  }
  try {
    const guestPayload = await verifyGuestToken(env, token);
    return { kind: "guest", guestId: guestPayload.sub };
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
  async fetch(request, env, ctx) {
    const preflight = corsPreflight(request);
    if (preflight) return preflight;
    try {
      const response = await handleRequest(request, env, ctx);
      return withCors(request, response);
    } catch (exc) {
      return withCors(
        request,
        json({ error: String(exc?.message || exc) }, 500)
      );
    }
  },
  async scheduled(_event, env) {
    try {
      const deleted = await cleanupPendingUsers(env.DB);
      console.log(`cleanupPendingUsers: deleted ${deleted}`);
    } catch (exc) {
      console.error("scheduled cleanup failed:", exc);
    }
    try {
      const handoffDeleted = await cleanupExpiredHandoffCodes(env.DB);
      console.log(`cleanupExpiredHandoffCodes: deleted ${handoffDeleted}`);
    } catch (exc) {
      console.error("scheduled handoff cleanup failed:", exc);
    }
    try {
      const followups = await processPaymentFollowups(env);
      console.log(`processPaymentFollowups: ${JSON.stringify(followups)}`);
    } catch (exc) {
      console.error("scheduled payment followups failed:", exc);
    }
  },
};

async function enforceRateLimit(request, env, scope) {
  const ip = clientIp(request);
  const result = await checkRateLimit(env.DB, `${scope}:${ip}`);
  if (!result.allowed) {
    return rateLimitResponse(result.retryAfterSec);
  }
  return null;
}

async function handleMobileSession(request, env) {
  const limited = await enforceRateLimit(request, env, "auth_login");
  if (limited) return limited;
  const body = await readJson(request);
  const email = (body.email || "").trim().toLowerCase();
  const password = body.password || "";
  const user = await userByEmail(env.DB, email);
  if (!user || !bcrypt.compareSync(password, user.password_hash)) {
    return textError("Invalid email or password.", 401);
  }
  const accountStatus = (user.account_status || "active").trim();
  if (accountStatus === "pending_payment") {
    return textError(
      "Your account is not active yet. Finish checkout on the subscribe page.",
      403
    );
  }
  const tokens = await issueTokens(env, user.id, user.email);
  let stripe;
  try {
    stripe = getStripe(env);
  } catch {
    return json({
      ...tokens,
      account: {
        email: user.email,
        active: false,
        storage_tier: "cloud",
        portal_url: null,
        email_verified: isEmailVerified(user),
      },
    });
  }
  const sub = await subscriptionStatus(stripe, user.stripe_customer_id);
  const portal = await portalUrl(stripe, user.stripe_customer_id);
  return json({
    ...tokens,
    account: {
      email: user.email,
      active: sub.active,
      storage_tier: "cloud",
      portal_url: portal,
      email_verified: isEmailVerified(user),
    },
  });
}

async function handleRequest(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";

    if (path === "/health" && request.method === "GET") {
      return json({ ok: true, stripe: Boolean(env.STRIPE_SECRET_KEY) });
    }

    if (path === "/checkout/session-info" && request.method === "GET") {
      return handleCheckoutSessionInfo(request, env, {
        getStripe,
        userById,
        subscriptionStatus,
      });
    }

    if (path === "/auth/signup" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "auth_signup");
      if (limited) return limited;
      return handleSignup(request, env, { userByEmail, userById });
    }

    if (path === "/checkout/create-session" && request.method === "POST") {
      return handleCreateCheckoutSession(request, env, {
        getStripe,
        requireUser,
        userById,
        subscriptionStatus,
      });
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
        const stripe = getStripe(env);
        ({ email, customerId } = await validatedCheckoutSession(stripe, sessionId));
      } catch (exc) {
        return textError(String(exc.message || exc), exc.message === "Stripe is not configured." ? 503 : 400);
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
        "INSERT INTO users (email, password_hash, stripe_customer_id, account_status, created_at) VALUES (?, ?, ?, 'active', ?)"
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
        const stripe = getStripe(env);
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
      let stripe;
      try {
        stripe = getStripe(env);
        ({ email, customerId } = await validatedCheckoutSession(stripe, sessionId));
      } catch (exc) {
        return textError(String(exc.message || exc), exc.message === "Stripe is not configured." ? 503 : 400);
      }
      if (email !== auth.user.email.trim().toLowerCase()) {
        return textError("Checkout email does not match your account.", 400);
      }
      await env.DB.prepare(
        "UPDATE users SET stripe_customer_id = ?, account_status = 'active' WHERE id = ?"
      )
        .bind(customerId, auth.user.id)
        .run();
      const tier = await resolveStorageTier(env.DB, stripe, {
        ...auth.user,
        stripe_customer_id: customerId,
      });
      return json({ ok: true, storage_tier: tier });
    }

    if (path === "/auth/login" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "auth_login");
      if (limited) return limited;
      const body = await readJson(request);
      const email = (body.email || "").trim().toLowerCase();
      const password = body.password || "";
      const user = await userByEmail(env.DB, email);
      if (!user || !bcrypt.compareSync(password, user.password_hash)) {
        return textError("Invalid email or password.", 401);
      }
      const accountStatus = (user.account_status || "active").trim();
      if (accountStatus === "pending_payment") {
        return textError(
          "Your account is not active yet. Finish checkout on the subscribe page.",
          403
        );
      }
      const tokens = await issueTokens(env, user.id, user.email);
      return json(tokens);
    }

    if (path === "/auth/handoff/create" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "auth_handoff_create");
      if (limited) return limited;
      return handleHandoffCreate(request, env, {
        requireUser,
        userById,
        subscriptionStatus,
        getStripe,
      });
    }

    if (path === "/auth/handoff/redeem" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "auth_handoff");
      if (limited) return limited;
      return handleHandoffRedeem(request, env, {
        userById,
        issueTokens,
        subscriptionStatus,
        getStripe,
      });
    }

    if (path === "/account/export" && request.method === "GET") {
      const limited = await enforceRateLimit(request, env, "account_export");
      if (limited) return limited;
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      return handleAccountExport(request, env, auth);
    }

    if (path === "/account/tax-export" && request.method === "GET") {
      const limited = await enforceRateLimit(request, env, "account_tax_export");
      if (limited) return limited;
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      return handleAccountTaxExport(request, env, auth);
    }

    if (path === "/account/data/delete" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "account_data_delete");
      if (limited) return limited;
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      return handleAccountDataDelete(request, env, auth);
    }

    if (path === "/account/delete" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "account_delete");
      if (limited) return limited;
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      return handleAccountDelete(request, env, auth, { bcrypt, getStripe });
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

    if (path === "/auth/forgot-password" && request.method === "POST") {
      const limited = await enforceRateLimit(request, env, "auth_forgot");
      if (limited) return limited;
      return handleForgotPassword(request, env, { userByEmail });
    }

    if (path === "/auth/reset-password" && request.method === "POST") {
      return handleResetPassword(request, env);
    }

    if (path === "/auth/verify-email" && request.method === "POST") {
      return handleVerifyEmail(request, env);
    }

    if (path === "/auth/resend-verification" && request.method === "POST") {
      return handleResendVerification(request, env, { requireUser });
    }

    if (path === "/entitlements" && request.method === "GET") {
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      let stripe;
      try {
        stripe = getStripe(env);
      } catch {
        return textError("Stripe is not configured.", 503);
      }
      const sub = await subscriptionStatus(stripe, auth.user.stripe_customer_id);
      sub.portal_url = await portalUrl(stripe, auth.user.stripe_customer_id);
      sub.storage_tier = "cloud";
      sub.platforms = entitlementsPlatforms("cloud");
      sub.email_verified = isEmailVerified(auth.user);
      sub.email = auth.user.email;
      await updateSubscriptionMilestones(env.DB, auth.user, sub);
      try {
        await processEmailOutbox(env, auth.user.id, auth.user.email);
      } catch {
        /* non-fatal */
      }
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

    if (path === "/metrics/summary" && request.method === "GET") {
      const auth = checkMetricsAuth(request, env.METRICS_TOKEN);
      if (!auth.ok) return auth.response;
      try {
        const summary = await buildMetricsSummary(env.DB);
        return json(summary);
      } catch (exc) {
        return textError(String(exc.message || exc), 500);
      }
    }

    if (path === "/devices/upsert" && request.method === "POST") {
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      const body = await readJson(request);
      try {
        await upsertAccountDevice(env.DB, auth.user.id, body);
        return json({ ok: true });
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
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

    const guestResponse = await handleGuestRoute(request, env, path);
    if (guestResponse) return guestResponse;

    const mobileResponse = await handleMobileRoute(request, env, path, {
      requireUser,
      getStripe,
      subscriptionStatus,
      portalUrl,
      handleDocumentsRoute,
      handleMobileSession,
      executionCtx: ctx,
    });
    if (mobileResponse) return mobileResponse;

    if (path.startsWith("/email/invoices/")) {
      const auth = await requireUser(request, env);
      if (auth.error) return auth.error;
      const relayResponse = await handleInvoiceRelaySend(request, env, auth, {
        getStripe,
        subscriptionStatus,
      });
      if (relayResponse) return relayResponse;
    }

    if (path.startsWith("/documents")) {
      const docAuth = await requireUserOrGuest(request, env);
      if (docAuth.error) return docAuth.error;
      if (docAuth.kind === "guest") {
        const docResponse = await handleGuestDocumentsRoute(request, env, path, docAuth.guestId);
        if (docResponse) return docResponse;
        return textError("Not found", 404);
      }
      let stripe;
      try {
        stripe = getStripe(env);
      } catch {
        return textError("Stripe is not configured.", 503);
      }
      const docResponse = await handleDocumentsRoute(
        request,
        env,
        path,
        docAuth,
        stripe,
        subscriptionStatus,
        ctx
      );
      if (docResponse) return docResponse;
    }

    if (path === "/dev/reset-seed" && request.method === "POST") {
      if (String(env.ALLOW_DEV_RESET || "") !== "1") {
        return textError("Not found", 404);
      }
      const auth = checkMetricsAuth(request, env.METRICS_TOKEN);
      if (!auth.ok) return auth.response;
      let stripe;
      try {
        stripe = getStripe(env);
      } catch (exc) {
        return textError(String(exc.message || exc), 503);
      }
      const result = await purgeAndSeedFromStripe(env, stripe);
      return json(result);
    }

    if (path === "/webhooks/stripe" && request.method === "POST") {
      return handleStripeWebhook(request, env, {
        getStripe,
        userById,
        subscriptionStatus,
      });
    }

    return textError("Not found", 404);
}
