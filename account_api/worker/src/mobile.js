import { loadCloudAccess } from "./documents.js";
import { isEmailVerified } from "./auth_email.js";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textError(message, status) {
  return json({ error: message }, status);
}

async function mobileAccount(env, auth, stripe, subscriptionStatus, portalUrl) {
  const access = await loadCloudAccess(env.DB, stripe, auth.user);
  const sub = access.active
    ? { active: true, status: access.status || "active" }
    : await subscriptionStatus(stripe, auth.user.stripe_customer_id);
  const portal = await portalUrl(stripe, auth.user.stripe_customer_id);
  return json({
    email: auth.user.email,
    active: Boolean(sub.active),
    storage_tier: "cloud",
    portal_url: portal,
    email_verified: isEmailVerified(auth.user),
    platforms: { desktop: true, mobile: true },
  });
}

async function requireCloudActive(env, auth, stripe) {
  const access = await loadCloudAccess(env.DB, stripe, auth.user);
  if (!access.active) {
    return { error: textError("Active subscription required.", 403) };
  }
  auth.cloudAccess = access;
  return { tier: "cloud", sub: { active: true }, access };
}

function mapMobileToDocumentsPath(path) {
  if (path === "/mobile/v1/bootstrap") return "/documents/bootstrap";
  if (path === "/mobile/v1/sync") return "/documents/sync";
  const invoicePdfMatch = path.match(/^\/mobile\/v1\/invoices\/([^/]+)\/pdf$/);
  if (invoicePdfMatch) return `/documents/invoices/${invoicePdfMatch[1]}/pdf`;
  const quotePdfMatch = path.match(/^\/mobile\/v1\/quotes\/([^/]+)\/pdf$/);
  if (quotePdfMatch) return `/documents/quotes/${quotePdfMatch[1]}/pdf`;
  return null;
}

export async function handleMobileRoute(request, env, path, deps) {
  if (!path.startsWith("/mobile/v1")) return null;

  const {
    requireUser,
    getStripe,
    subscriptionStatus,
    portalUrl,
    handleDocumentsRoute,
    handleMobileSession,
    executionCtx = null,
  } = deps;

  if (path === "/mobile/v1/session" && request.method === "POST") {
    return handleMobileSession(request, env);
  }

  const auth = await requireUser(request, env);
  if (auth.error) return auth.error;

  let stripe;
  try {
    stripe = getStripe(env);
  } catch {
    return textError("Stripe is not configured.", 503);
  }

  if (path === "/mobile/v1/account" && request.method === "GET") {
    return mobileAccount(env, auth, stripe, subscriptionStatus, portalUrl);
  }

  const gate = await requireCloudActive(env, auth, stripe);
  if (gate.error) return gate.error;

  const docPath = mapMobileToDocumentsPath(path);
  if (!docPath) return textError("Not found", 404);

  return handleDocumentsRoute(
    request,
    env,
    docPath,
    auth,
    stripe,
    subscriptionStatus,
    executionCtx
  );
}
