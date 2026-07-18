import { createHandoff, mapAuthError } from "./api.js";
import { PWA_URL, SESSION_KEYS, authHeader } from "./config.js";

const params = new URLSearchParams(location.search);
const flow = params.get("flow") || "login";
const email = params.get("email") || "";

const titleEl = document.getElementById("success-title");
const leadEl = document.getElementById("success-lead");
const emailWrap = document.getElementById("success-email");
const emailStrong = emailWrap?.querySelector("strong");
const errorEl = document.getElementById("success-error");
const openBtn = document.getElementById("open-pwa");
const openHint = document.getElementById("open-pwa-hint");
const installSection = document.getElementById("install-section");

const displayEmail = email || sessionStorage.getItem(SESSION_KEYS.signupEmail) || "";
if (displayEmail && emailStrong) {
  emailStrong.textContent = displayEmail;
  if (emailWrap) emailWrap.hidden = false;
}

if (flow === "subscribe" || flow === "register") {
  if (titleEl) titleEl.textContent = "Subscription active";
  if (leadEl) {
    leadEl.textContent =
      "Open FrogsWork in your browser to start invoicing. You can also install it on Windows, iPhone, or Android.";
  }
} else if (flow === "upgrade") {
  if (titleEl) titleEl.textContent = "Plan updated";
  if (leadEl) {
    leadEl.textContent = "Cloud is active. Open the app to continue.";
  }
} else if (flow === "login") {
  if (titleEl) titleEl.textContent = "Signed in";
  if (leadEl) {
    leadEl.textContent = "Open FrogsWork in your browser to continue.";
  }
  if (installSection) installSection.hidden = true;
}

function showError(text) {
  if (!errorEl) return;
  errorEl.textContent = text;
  errorEl.hidden = !text;
}

async function openApp() {
  showError("");
  const token = authHeader();
  if (!token) {
    showError("Your session expired. Sign in again, then open the app.");
    if (openHint) {
      openHint.innerHTML = `<a href="/account/login.html?next=pwa">Sign in to open the app</a>`;
    }
    return;
  }
  if (openBtn) {
    openBtn.disabled = true;
    openBtn.textContent = "Opening…";
  }
  try {
    const result = await createHandoff(token);
    if (!result.code) throw new Error("Handoff failed");
    sessionStorage.removeItem(SESSION_KEYS.signupToken);
    window.location.href = `${PWA_URL}/?handoff=${encodeURIComponent(result.code)}`;
  } catch (err) {
    if (openBtn) {
      openBtn.disabled = false;
      openBtn.textContent = "Open FrogsWork in browser";
    }
    showError(
      mapAuthError(err.message) ||
        "Could not open the app automatically. Sign in on the app page."
    );
    if (openHint) {
      openHint.innerHTML = `Or open <a data-fw-open-app="success" href="${PWA_URL}">${PWA_URL.replace(/^https?:\/\//, "")}</a> and sign in.`;
    }
  }
}

openBtn?.addEventListener("click", () => {
  void openApp();
});
