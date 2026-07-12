import { getCheckoutSessionInfo, register, mapAuthError } from "./api.js";
import { SESSION_KEYS } from "./config.js";

const sessionId = sessionStorage.getItem(SESSION_KEYS.checkoutSessionId) || "";
const installId = sessionStorage.getItem(SESSION_KEYS.installId) || "";
const loadingEl = document.getElementById("create-loading");
const existsEl = document.getElementById("create-exists");
const formEl = document.getElementById("create-form");
const emailEl = document.getElementById("create-email");
const errorEl = document.getElementById("create-error");

function showError(text) {
  if (!errorEl) return;
  errorEl.textContent = text;
  errorEl.hidden = !text;
}

if (!sessionId.startsWith("cs_")) {
  window.location.replace("/account/subscribe.html");
} else {
  getCheckoutSessionInfo(sessionId)
    .then((info) => {
      if (loadingEl) loadingEl.hidden = true;
      if (!info.paid || !info.email) {
        window.location.replace("/account/subscribe.html");
        return;
      }
      if (emailEl) emailEl.textContent = info.email;
      const formEmail = document.getElementById("create-email-form");
      if (formEmail) formEmail.textContent = info.email;
      if (info.account_exists) {
        if (existsEl) existsEl.hidden = false;
        const loginLink = document.getElementById("create-login-link");
        if (loginLink) {
          loginLink.href = `/account/login.html?email=${encodeURIComponent(info.email)}`;
        }
        return;
      }
      if (formEl) formEl.hidden = false;
    })
    .catch((err) => {
      if (loadingEl) loadingEl.hidden = true;
      showError(err.message || "Could not load checkout details.");
    });
}

formEl?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("password")?.value || "";
  const confirm = document.getElementById("password_confirm")?.value || "";
  if (password.length < 8) {
    showError("Password must be at least 8 characters.");
    return;
  }
  if (password !== confirm) {
    showError("Passwords do not match.");
    return;
  }
  showError("");
  const btn = formEl.querySelector('button[type="submit"]');
  if (btn) btn.disabled = true;
  try {
    const tokens = await register(password, sessionId, installId || undefined);
    sessionStorage.removeItem(SESSION_KEYS.checkoutSessionId);
    sessionStorage.setItem("fw_access_token", tokens.access_token);
    sessionStorage.setItem("fw_refresh_token", tokens.refresh_token || "");
    window.location.href = `/account/success.html?flow=register&email=${encodeURIComponent(tokens.email || "")}`;
  } catch (err) {
    if (btn) btn.disabled = false;
    showError(mapAuthError(err.message));
  }
});
