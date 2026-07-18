import { login, attachCheckout, createHandoff, mapAuthError } from "./api.js";
import { PWA_URL, SESSION_KEYS } from "./config.js";

const params = new URLSearchParams(location.search);
const next = params.get("next") || "";
const presetEmail = params.get("email") || "";
const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const emailInput = document.getElementById("email");

if (presetEmail && emailInput) {
  emailInput.value = presetEmail;
}

async function openAppWithHandoff(tokens) {
  sessionStorage.setItem(SESSION_KEYS.accessToken, tokens.access_token);
  if (tokens.refresh_token) {
    sessionStorage.setItem(SESSION_KEYS.refreshToken, tokens.refresh_token);
  }
  try {
    const result = await createHandoff(tokens.access_token);
    if (!result.code) throw new Error("Handoff failed");
    window.location.href = `${PWA_URL}/?handoff=${encodeURIComponent(result.code)}`;
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = mapAuthError(err.message) || "Could not open the app. Try again.";
      errorEl.hidden = false;
    }
  }
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
    if (next === "pwa" || next === "desktop" || next === "app") {
      void openAppWithHandoff(tokens);
      return;
    }
    sessionStorage.setItem(SESSION_KEYS.accessToken, tokens.access_token);
    if (tokens.refresh_token) {
      sessionStorage.setItem(SESSION_KEYS.refreshToken, tokens.refresh_token);
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
