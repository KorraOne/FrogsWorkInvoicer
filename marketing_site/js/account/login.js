import { login, attachCheckout, mapAuthError } from "./api.js";
import { DESKTOP_CALLBACK_URL, PWA_URL, SESSION_KEYS } from "./config.js";

const params = new URLSearchParams(location.search);
const next = params.get("next") || "";
const presetEmail = params.get("email") || "";
const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const emailInput = document.getElementById("email");

if (presetEmail && emailInput) {
  emailInput.value = presetEmail;
}

function redirectAfterLogin(tokens, email) {
  const checkoutSessionId = sessionStorage.getItem(SESSION_KEYS.checkoutSessionId);

  const finishSubscribe = () => {
    sessionStorage.setItem(SESSION_KEYS.accessToken, tokens.access_token);
    if (tokens.refresh_token) {
      sessionStorage.setItem(SESSION_KEYS.refreshToken, tokens.refresh_token);
    }
    sessionStorage.removeItem(SESSION_KEYS.signupToken);
    const q = new URLSearchParams(location.search);
    q.delete("next");
    q.delete("email");
    const suffix = q.toString();
    window.location.href = `/account/subscribe.html${suffix ? `?${suffix}` : ""}`;
  };

  const finish = () => {
    if (next === "subscribe") {
      finishSubscribe();
      return;
    }
    if (next === "pwa") {
      const q = new URLSearchParams({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token || "",
      });
      window.location.href = `${PWA_URL}/#auth/callback?${q}`;
      return;
    }
    if (next === "desktop") {
      const q = new URLSearchParams({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token || "",
        email,
      });
      window.location.href = `${DESKTOP_CALLBACK_URL}?${q}`;
      return;
    }
    window.location.href = "/account/success.html?flow=login";
  };

  if (checkoutSessionId?.startsWith("cs_")) {
    attachCheckout(checkoutSessionId, tokens.access_token)
      .catch((err) => {
        if (errorEl) {
          errorEl.textContent = mapAuthError(err.message);
          errorEl.hidden = false;
        }
      })
      .finally(() => {
        sessionStorage.removeItem(SESSION_KEYS.checkoutSessionId);
        if (next === "subscribe") {
          finishSubscribe();
        } else {
          finish();
        }
      });
    return;
  }
  finish();
}

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = emailInput?.value?.trim() || "";
  const password = document.getElementById("password")?.value || "";
  if (errorEl) errorEl.hidden = true;
  const btn = form.querySelector('button[type="submit"]');
  if (btn) btn.disabled = true;
  try {
    const tokens = await login(email, password);
    redirectAfterLogin(tokens, email);
  } catch (err) {
    if (btn) btn.disabled = false;
    if (errorEl) {
      errorEl.textContent = mapAuthError(err.message);
      errorEl.hidden = false;
    }
  }
});
