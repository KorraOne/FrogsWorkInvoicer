import { createCheckoutSession, mapAuthError } from "./api.js";
import { SESSION_KEYS, authHeader } from "./config.js";

const params = new URLSearchParams(location.search);
const installId = params.get("install_id");
const isUpgrade = params.get("upgrade") === "1" || params.get("upgrade") === "cloud";
const promoCode = (params.get("promo") || "").trim();

if (installId) {
  sessionStorage.setItem(SESSION_KEYS.installId, installId);
}

const errorEl = document.getElementById("subscribe-error");
const emailWrap = document.getElementById("subscribe-email");
const emailStrong = emailWrap?.querySelector("strong");
const heading = document.getElementById("subscribe-heading");
const lead = document.getElementById("subscribe-lead");

function showError(text) {
  if (!errorEl) return;
  errorEl.textContent = text;
  errorEl.hidden = !text;
}

function ensureAuth() {
  const token = authHeader();
  if (token) return token;
  const q = new URLSearchParams(location.search);
  if (isUpgrade) {
    q.set("next", "subscribe");
    window.location.replace(`/account/login.html?${q}`);
  } else {
    window.location.replace(`/account/signup.html?${q}`);
  }
  return null;
}

async function startCheckout(interval) {
  const token = ensureAuth();
  if (!token) return;
  showError("");
  const buttons = document.querySelectorAll(".tier-plan-btn");
  buttons.forEach((b) => {
    b.disabled = true;
  });
  try {
    const billingInterval = interval === "year" ? "year" : "month";
    const result = await createCheckoutSession("cloud", billingInterval, token, promoCode || undefined);
    if (result.upgraded) {
      if (window.fwGa) {
        window.fwGa.track("purchase", { tier: "cloud", interval: billingInterval, flow: "upgrade" });
      }
      sessionStorage.removeItem(SESSION_KEYS.signupToken);
      window.location.href = `/account/success.html?flow=upgrade&tier=cloud`;
      return;
    }
    if (result.checkout_url) {
      if (window.fwGa) {
        window.fwGa.track("begin_checkout", { tier: "cloud", interval: billingInterval });
      }
      window.location.href = result.checkout_url;
      return;
    }
    showError("Checkout could not be started. Try again or contact support.");
  } catch (err) {
    showError(mapAuthError(err.message));
  } finally {
    buttons.forEach((b) => {
      b.disabled = false;
    });
  }
}

document.querySelectorAll("[data-checkout-tier]").forEach((btn) => {
  btn.addEventListener("click", () => {
    startCheckout(btn.dataset.interval === "year" ? "year" : "month");
  });
});

const storedEmail = sessionStorage.getItem(SESSION_KEYS.signupEmail);
if (storedEmail && emailStrong) {
  emailStrong.textContent = storedEmail;
  if (emailWrap) emailWrap.hidden = false;
}

if (isUpgrade) {
  if (heading) heading.textContent = "Upgrade to Cloud";
  if (lead) {
    lead.textContent =
      "Cloud keeps the same invoices on browser, phone, and Windows. Checkout uses your account email. New subscriptions include a 14-day trial.";
  }
}

if (!authHeader()) {
  ensureAuth();
}
