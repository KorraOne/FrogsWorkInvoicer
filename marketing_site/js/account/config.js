const isLocal = location.hostname === "127.0.0.1" || location.hostname === "localhost";

function queryApiBase() {
  const q = new URLSearchParams(location.search).get("api");
  if (q) return q.replace(/\/$/, "");
  const stored = localStorage.getItem("frogswork_api");
  if (stored) return stored.replace(/\/$/, "");
  return isLocal ? "http://127.0.0.1:8787" : "https://api.frogswork.com";
}

export const API_BASE = queryApiBase();
export const PWA_URL = isLocal ? "http://127.0.0.1:5173" : "https://app.frogswork.com";
export const TERMS_URL = "/terms.html";
export const PRIVACY_URL = "/privacy.html";

/** Optional shareable Payment Links (manual use). Prefer API checkout. */
export const PAYMENT_LINKS = {
  monthly: "https://buy.stripe.com/4gM28sg3Qcpn8Od26x8Zq04",
  annual: "https://buy.stripe.com/fZudRa6tg60Z2pPdPf8Zq05",
};

export const PLANS = {
  local: {
    monthly: { display: "$9.99/mo", interval: "month" },
    annual: { display: "$99/yr", interval: "year" },
  },
  cloud: {
    monthly: { display: "$14.99/mo", interval: "month" },
    annual: { display: "$149/yr", interval: "year" },
  },
};

export function paymentLinkForPlan(plan) {
  const key = plan === "annual" ? "annual" : "monthly";
  const fromStorage = localStorage.getItem(`stripe_link_${key}`);
  if (fromStorage) return fromStorage;
  return PAYMENT_LINKS[key] || "";
}

export const SESSION_KEYS = {
  checkoutSessionId: "fw_checkout_session_id",
  installId: "fw_install_id",
  signupToken: "fw_signup_token",
  signupEmail: "fw_signup_email",
  accessToken: "fw_access_token",
  refreshToken: "fw_refresh_token",
};

export function authHeader() {
  const access = sessionStorage.getItem(SESSION_KEYS.accessToken);
  if (access) return access;
  return sessionStorage.getItem(SESSION_KEYS.signupToken) || "";
}

export function subscribeUrl({ upgrade = false, tier = "" } = {}) {
  const params = new URLSearchParams();
  if (upgrade) params.set("upgrade", "1");
  if (tier) params.set("tier", tier);
  const q = params.toString();
  return `/account/subscribe.html${q ? `?${q}` : ""}`;
}
