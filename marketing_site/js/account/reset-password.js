import { apiRequest } from "./api.js";

const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const form = document.getElementById("reset-form");
const messageEl = document.getElementById("reset-message");

function showMessage(text, ok = false) {
  if (!messageEl) return;
  messageEl.textContent = text;
  messageEl.hidden = !text;
  messageEl.className = ok ? "account-success" : "account-error";
}

if (!token) {
  showMessage("Missing reset token. Request a new link from the forgot password page.");
  form?.querySelector("button")?.setAttribute("disabled", "disabled");
}

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage("");
  const fd = new FormData(form);
  const password = fd.get("password");
  const password2 = fd.get("password2");
  if (password !== password2) {
    showMessage("Passwords do not match.");
    return;
  }
  try {
    await apiRequest("POST", "/auth/reset-password", { token, password });
    showMessage("Password updated. You can sign in now.", true);
    form.reset();
    setTimeout(() => {
      window.location.href = "/account/login.html";
    }, 1500);
  } catch (err) {
    showMessage(err.message || "Could not reset password.");
  }
});
