import { createCheckoutSession, mapAuthError } from "./api.js";
import { PLANS, SESSION_KEYS, authHeader } from "./config.js";

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

let selectedInterval = "month";

function showError(text) {
  if (!errorEl) return;
  errorEl.textContent = text;
  errorEl.hidden = !text;
}

function updatePrices() {
  const cloudPlan = PLANS.cloud[selectedInterval === "year" ? "annual" : "monthly"];
  const cloudEl = document.querySelector("[data-price-cloud]");
  if (cloudEl) cloudEl.textContent = cloudPlan.display;
}

document.querySelectorAll(".billing-toggle-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    selectedInterval = btn.dataset.interval === "year" ? "year" : "month";
    document.querySelectorAll(".billing-toggle-btn").forEach((b) => {
      b.classList.toggle("billing-toggle-btn--active", b === btn);
    });
    updatePrices();
  });
});

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

async function startCheckout() {
  const token = ensureAuth();
  if (!token) return;
  showError("");
  const buttons = document.querySelectorAll(".tier-plan-btn");
  buttons.forEach((b) => {
    b.disabled = true;
  });
  try {
    const interval = selectedInterval === "year" ? "year" : "month";
    const result = await createCheckoutSession("cloud", interval, token, promoCode || undefined);
    if (result.upgraded) {
      sessionStorage.removeItem(SESSION_KEYS.signupToken);
      window.location.href = `/account/success.html?flow=upgrade&tier=cloud`;
      return;
    }
    if (result.checkout_url) {
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
    startCheckout();
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
      "Cloud keeps the same invoices on browser, phone, and Windows. Checkout uses your account email.";
  }
}

updatePrices();

if (!authHeader()) {
  ensureAuth();
}
