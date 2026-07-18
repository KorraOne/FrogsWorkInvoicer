import bcrypt from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import { jwtSecretBytes } from "./jwt_secret.js";
import {
  isValidInstallId,
  linkInstallOnRegister,
  updateSubscriptionMilestones,
} from "./telemetry.js";
import { resolveStorageTier, storageTierFromSubscription } from "./documents.js";
import { sendVerificationEmail } from "./auth_email.js";

async function resolvePromotionCodeId(stripe, code) {
  const normalized = (code || "").trim();
  if (!normalized) return null;
  const list = await stripe.promotionCodes.list({
    code: normalized,
    active: true,
    limit: 1,
  });
  return list.data[0]?.id || null;
}

/** Optional URL/body promo only — manage coupons in Stripe Dashboard. */
async function buildCheckoutDiscounts(stripe, body) {
  const urlCode = (body.promotion_code || "").trim();
  if (urlCode && stripe) {
    const resolved = await resolvePromotionCodeId(stripe, urlCode);
    if (resolved) {
      return {
        discounts: [{ promotion_code: resolved }],
        allow_promotion_codes: true,
      };
    }
  }
  return { discounts: undefined, allow_promotion_codes: true };
}

const SIGNUP_TTL_SEC = 24 * 60 * 60;
const PENDING_TTL_DAYS = 7;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status) {
  return json({ error: message }, status);
}

function checkoutReturnBase(request, env) {
  const origin = request.headers.get("Origin") || "";
  if (origin.includes("127.0.0.1") || origin.includes("localhost")) {
    return origin.replace(/\/$/, "");
  }
  const configured = (env.CHECKOUT_RETURN_BASE || "").trim();
  return configured || "https://frogswork.com";
}

export function priceIdForPlan(env, tier, interval) {
  const t = tier === "cloud" ? "cloud" : "local";
  const i = interval === "year" ? "annual" : "monthly";
  const key = `STRIPE_PRICE_${t.toUpperCase()}_${i.toUpperCase()}`;
  const id = (env[key] || "").trim();
  if (!id) {
    throw new Error(`Stripe price not configured for ${t} ${i}.`);
  }
  return id;
}

function sessionEmail(checkout) {
  return (
    checkout.customer_details?.email ||
    checkout.customer_email ||
    ""
  )
    .trim()
    .toLowerCase();
}

export async function issueSignupToken(env, userId, email) {
  const secret = jwtSecretBytes(env);
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({
    sub: String(userId),
    email,
    type: "signup",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + SIGNUP_TTL_SEC)
    .sign(secret);
}

export async function decodeSignupToken(env, token) {
  const secret = jwtSecretBytes(env);
  const { payload } = await jwtVerify(token, secret);
  if (payload.type !== "signup") {
    throw new Error("Invalid signup token.");
  }
  return payload;
}

export async function authFromCheckoutRequest(request, env, requireUserFn) {
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Bearer ")) {
    return { error: textError("Unauthorized", 401) };
  }
  const token = header.slice(7);
  try {
    const payload = await decodeSignupToken(env, token);
    const user = await requireUserFn.userById(env.DB, Number(payload.sub));
    if (!user) {
      return { error: textError("Unauthorized", 401) };
    }
    if (user.email !== (payload.email || "").trim().toLowerCase()) {
      return { error: textError("Unauthorized", 401) };
    }
    return { user, kind: "signup" };
  } catch {
    /* try access token */
  }
  const auth = await requireUserFn.requireUser(request, env);
  if (auth.error) return auth;
  return { user: auth.user, kind: "access" };
}

export async function handleSignup(request, env, { userByEmail, userById }) {
  const body = await request.json().catch(() => ({}));
  const email = (body.email || "").trim().toLowerCase();
  const password = body.password || "";
  if (!email || !email.includes("@")) {
    return textError("A valid email is required.", 400);
  }
  if (!password || password.length < 8) {
    return textError("Password must be at least 8 characters.", 400);
  }

  const existing = await userByEmail(env.DB, email);
  if (existing) {
    const status = (existing.account_status || "active").trim();
    if (status === "pending_payment") {
      if (!bcrypt.compareSync(password, existing.password_hash)) {
        return textError(
          "Could not create account. Check your details or sign in.",
          400
        );
      }
      const signupToken = await issueSignupToken(env, existing.id, email);
      return json({
        signup_token: signupToken,
        email,
        account_status: "pending_payment",
        resumed: true,
      });
    }
    return textError(
      "An account with this email already exists. Sign in instead.",
      409
    );
  }

  const passwordHash = bcrypt.hashSync(password, 10);
  const createdAt = new Date().toISOString();
  const result = await env.DB.prepare(
    `INSERT INTO users (email, password_hash, stripe_customer_id, storage_tier, account_status, created_at)
     VALUES (?, ?, NULL, 'local', 'pending_payment', ?)`
  )
    .bind(email, passwordHash, createdAt)
    .run();

  const userId = result.meta.last_row_id;
  const signupToken = await issueSignupToken(env, userId, email);
  try {
    const user = await userById(env.DB, userId);
    if (user) await sendVerificationEmail(env, request, user);
  } catch (exc) {
    console.error("signup verification email failed:", exc);
  }
  return json({
    signup_token: signupToken,
    email,
    account_status: "pending_payment",
    resumed: false,
  });
}

async function activeSubscription(stripe, customerId) {
  if (!customerId) return null;
  const subs = await stripe.subscriptions.list({
    customer: customerId,
    status: "all",
    limit: 5,
  });
  for (const sub of subs.data) {
    if (sub.status === "active" || sub.status === "trialing") {
      return sub;
    }
  }
  return null;
}

export async function handleCreateCheckoutSession(
  request,
  env,
  { getStripe, requireUser, userById, subscriptionStatus }
) {
  const auth = await authFromCheckoutRequest(request, env, {
    requireUser,
    userById,
  });
  if (auth.error) return auth.error;

  const body = await request.json().catch(() => ({}));
  const tier = (body.tier || "local").toLowerCase() === "cloud" ? "cloud" : "local";
  const interval = (body.interval || "month").toLowerCase() === "year" ? "year" : "month";

  let priceId;
  try {
    priceId = priceIdForPlan(env, tier, interval);
  } catch (exc) {
    return textError(String(exc.message || exc), 503);
  }

  const user = auth.user;
  const status = (user.account_status || "active").trim();
  if (status === "pending_payment" && auth.kind !== "signup") {
    return textError("Use your signup link to continue checkout.", 403);
  }

  let stripe;
  try {
    stripe = getStripe(env);
  } catch (exc) {
    return textError(String(exc.message || exc), 503);
  }

  const base = checkoutReturnBase(request, env);
  const successUrl = `${base}/account/return.html?session_id={CHECKOUT_SESSION_ID}`;
  const cancelUrl = `${base}/account/subscribe.html`;

  const existingSub = await activeSubscription(stripe, user.stripe_customer_id);
  if (existingSub && auth.kind === "access" && status === "active") {
    const currentInterval =
      existingSub.items?.data?.[0]?.price?.recurring?.interval || "";
    if (currentInterval === interval) {
      try {
        const itemId = existingSub.items.data[0].id;
        const updated = await stripe.subscriptions.update(existingSub.id, {
          items: [{ id: itemId, price: priceId }],
          proration_behavior: "create_prorations",
          metadata: { storage_tier: tier },
        });
        await env.DB.prepare("UPDATE users SET storage_tier = ? WHERE id = ?")
          .bind(tier, user.id)
          .run();
        return json({
          upgraded: true,
          storage_tier: tier,
          subscription_id: updated.id,
        });
      } catch (exc) {
        return textError(String(exc.message || exc), 400);
      }
    }
  }

  const discountOpts = await buildCheckoutDiscounts(stripe, body);
  const sessionParams = {
    mode: "subscription",
    customer_email: user.email,
    line_items: [{ price: priceId, quantity: 1 }],
    allow_promotion_codes: discountOpts.allow_promotion_codes,
    success_url: successUrl,
    cancel_url: cancelUrl,
    client_reference_id: String(user.id),
    metadata: {
      user_id: String(user.id),
      storage_tier: tier,
    },
    subscription_data: {
      metadata: { storage_tier: tier },
      trial_period_days: 14,
    },
  };
  if (discountOpts.discounts?.length) {
    sessionParams.discounts = discountOpts.discounts;
  }
  const session = await stripe.checkout.sessions.create(sessionParams);

  return json({ checkout_url: session.url, session_id: session.id });
}

export async function checkoutSessionDetails(stripe, sessionId, db, userById) {
  const checkout = await stripe.checkout.sessions.retrieve(sessionId, {
    expand: ["subscription", "line_items"],
  });

  const paid =
    checkout.payment_status === "paid" || checkout.status === "complete";

  let email = sessionEmail(checkout);
  let storageTier = (checkout.metadata?.storage_tier || "local").toLowerCase();
  let accountStatus = null;

  const userId = Number(
    checkout.metadata?.user_id || checkout.client_reference_id || 0
  );
  if (userId) {
    const user = await userById(db, userId);
    if (user) {
      accountStatus = user.account_status || "active";
      if (!email) email = user.email;
    }
  }

  let sub = checkout.subscription;
  if (typeof sub === "string" && sub) {
    sub = await stripe.subscriptions.retrieve(sub);
  }
  if (sub && (sub.status === "active" || sub.status === "trialing")) {
    storageTier = storageTierFromSubscription(sub);
  }

  return {
    checkout,
    paid,
    email,
    storage_tier: storageTier === "cloud" ? "cloud" : "local",
    account_status: accountStatus,
    subscription_active: Boolean(
      sub && (sub.status === "active" || sub.status === "trialing")
    ),
  };
}

export async function activateUserFromCheckout(env, stripe, checkout, {
  userById,
  issueTokens,
  subscriptionStatus,
}) {
  const userId = Number(
    checkout.metadata?.user_id || checkout.client_reference_id || 0
  );
  if (!userId) {
    throw new Error("Checkout missing user reference.");
  }
  const user = await userById(env.DB, userId);
  if (!user) {
    throw new Error("User not found for checkout.");
  }

  const email = sessionEmail(checkout);
  if (email && email !== user.email.trim().toLowerCase()) {
    throw new Error("Checkout email does not match account.");
  }

  let customerId = checkout.customer;
  if (typeof customerId === "object" && customerId?.id) {
    customerId = customerId.id;
  }
  if (!customerId) {
    throw new Error("Checkout missing customer.");
  }

  let sub = checkout.subscription;
  if (typeof sub === "string") {
    sub = await stripe.subscriptions.retrieve(sub);
  }
  if (!sub || (sub.status !== "active" && sub.status !== "trialing")) {
    throw new Error("No active subscription on checkout.");
  }

  const tier = storageTierFromSubscription(sub);
  await env.DB.prepare(
    `UPDATE users SET stripe_customer_id = ?, account_status = 'active', storage_tier = ? WHERE id = ?`
  )
    .bind(customerId, tier, userId)
    .run();

  const updated = await userById(env.DB, userId);
  const subStatus = await subscriptionStatus(stripe, customerId);
  await updateSubscriptionMilestones(env.DB, updated, subStatus);

  return { user: updated, tier };
}

export async function handleCheckoutSessionInfo(
  request,
  env,
  { getStripe, userById, subscriptionStatus }
) {
  const url = new URL(request.url);
  const sessionId = (url.searchParams.get("session_id") || "").trim();
  if (!sessionId.startsWith("cs_")) {
    return textError("Invalid checkout session.", 400);
  }
  let stripe;
  try {
    stripe = getStripe(env);
  } catch {
    return textError("Stripe is not configured.", 503);
  }

  try {
    const details = await checkoutSessionDetails(
      stripe,
      sessionId,
      env.DB,
      userById
    );
    if (!details.paid) {
      return json({
        paid: false,
        email: details.email || null,
        subscription_active: false,
        storage_tier: details.storage_tier,
        account_status: details.account_status,
      });
    }
    if (!details.subscription_active) {
      return textError("No active subscription on this checkout.", 400);
    }

    try {
      await activateUserFromCheckout(env, stripe, details.checkout, {
        userById,
        subscriptionStatus,
        issueTokens: async () => ({}),
      });
    } catch {
      /* idempotent — may already be active */
    }

    const refreshed = await checkoutSessionDetails(
      stripe,
      sessionId,
      env.DB,
      userById
    );
    return json({
      email: refreshed.email,
      paid: true,
      subscription_active: true,
      storage_tier: refreshed.storage_tier,
      account_status: "active",
    });
  } catch (exc) {
    return textError(String(exc.message || exc), 400);
  }
}

export async function handleStripeWebhook(request, env, {
  getStripe,
  userById,
  subscriptionStatus,
}) {
  if (!env.STRIPE_WEBHOOK_SECRET) {
    return textError("Webhook secret not configured.", 500);
  }
  let stripe;
  try {
    stripe = getStripe(env);
  } catch {
    return textError("Stripe is not configured.", 500);
  }
  const payload = await request.text();
  const sig = request.headers.get("Stripe-Signature") || "";
  let event;
  try {
    event = stripe.webhooks.constructEvent(
      payload,
      sig,
      env.STRIPE_WEBHOOK_SECRET
    );
  } catch (exc) {
    return textError(String(exc.message || exc), 400);
  }

  if (event.type === "checkout.session.completed") {
    const checkout = event.data.object;
    if (checkout.mode === "subscription") {
      try {
        await activateUserFromCheckout(env, stripe, checkout, {
          userById,
          subscriptionStatus,
          issueTokens: async () => ({}),
        });
      } catch (exc) {
        console.error("checkout.session.completed activation failed:", exc);
      }
    }
  }

  return json({ received: true });
}

export async function cleanupPendingUsers(db) {
  const cutoff = new Date(
    Date.now() - PENDING_TTL_DAYS * 24 * 60 * 60 * 1000
  ).toISOString();
  const result = await db
    .prepare(
      `DELETE FROM users
       WHERE account_status = 'pending_payment'
         AND stripe_customer_id IS NULL
         AND created_at < ?`
    )
    .bind(cutoff)
    .run();
  return result.meta?.changes || 0;
}
