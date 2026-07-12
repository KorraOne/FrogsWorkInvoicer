import { getCheckoutSessionInfo } from "./api.js";
import { SESSION_KEYS } from "./config.js";

const statusEl = document.getElementById("return-status");
const errorEl = document.getElementById("return-error");

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

function showError(text) {
  if (errorEl) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }
}

const sessionId = new URLSearchParams(location.search).get("session_id")?.trim() || "";

if (!sessionId.startsWith("cs_")) {
  showError("Payment return is missing a valid session ID. Try subscribing again.");
} else {
  sessionStorage.setItem(SESSION_KEYS.checkoutSessionId, sessionId);
  setStatus("Confirming your payment…");

  async function poll(attempt = 0) {
    try {
      const info = await getCheckoutSessionInfo(sessionId);
      if (info.paid && info.account_status === "active") {
        sessionStorage.removeItem(SESSION_KEYS.signupToken);
        const tier = info.storage_tier || "local";
        window.location.replace(
          `/account/success.html?flow=subscribe&tier=${encodeURIComponent(tier)}&email=${encodeURIComponent(info.email || "")}`
        );
        return;
      }
      if (info.paid === false && attempt < 40) {
        setStatus("Waiting for Stripe to confirm payment…");
        setTimeout(() => poll(attempt + 1), 1500);
        return;
      }
      if (attempt > 40) {
        showError("Payment is taking longer than expected. Refresh this page in a moment.");
        return;
      }
      setStatus("Waiting for Stripe to confirm payment…");
      setTimeout(() => poll(attempt + 1), 1500);
    } catch (err) {
      if (attempt > 5) {
        showError(err.message || "Could not verify payment. Check your connection and refresh.");
        return;
      }
      setTimeout(() => poll(attempt + 1), 2000);
    }
  }

  poll();
}
