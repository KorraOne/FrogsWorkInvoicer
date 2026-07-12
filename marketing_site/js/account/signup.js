import { signup, mapAuthError } from "./api.js";
import { SESSION_KEYS } from "./config.js";

const form = document.getElementById("signup-form");
const errorEl = document.getElementById("signup-error");

function showError(text) {
  if (!errorEl) return;
  errorEl.textContent = text;
  errorEl.hidden = !text;
}

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("email")?.value?.trim() || "";
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
  if (!form.querySelector('input[name="accept_terms"]')?.checked) {
    showError("Accept the Terms and Privacy Policy to continue.");
    return;
  }
  showError("");
  const btn = form.querySelector('button[type="submit"]');
  if (btn) btn.disabled = true;
  try {
    const result = await signup(email, password);
    sessionStorage.setItem(SESSION_KEYS.signupToken, result.signup_token);
    sessionStorage.setItem(SESSION_KEYS.signupEmail, result.email || email);
    const params = new URLSearchParams(location.search);
    const tier = params.get("tier");
    const upgrade = params.get("upgrade");
    const next = new URLSearchParams();
    if (tier) next.set("tier", tier);
    if (upgrade) next.set("upgrade", "1");
    const q = next.toString();
    window.location.href = `/account/subscribe.html${q ? `?${q}` : ""}`;
  } catch (err) {
    if (btn) btn.disabled = false;
    const msg = mapAuthError(err.message);
    if (msg.toLowerCase().includes("already")) {
      showError(msg);
      if (!form.querySelector(".signup-exists-link")) {
        const link = document.createElement("p");
        link.className = "form-footer signup-exists-link";
        link.innerHTML = `<a href="/account/login.html?email=${encodeURIComponent(email)}">Sign in</a>`;
        form.appendChild(link);
      }
      return;
    }
    showError(msg);
  }
});
