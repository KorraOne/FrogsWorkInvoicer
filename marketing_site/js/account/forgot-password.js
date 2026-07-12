import { apiRequest } from "./api.js";

const form = document.getElementById("forgot-form");
const messageEl = document.getElementById("forgot-message");

function showMessage(text, ok = false) {
  if (!messageEl) return;
  messageEl.textContent = text;
  messageEl.hidden = !text;
  messageEl.className = ok ? "account-success" : "account-error";
}

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage("");
  const email = new FormData(form).get("email");
  try {
    await apiRequest("POST", "/auth/forgot-password", { email });
    showMessage("If that email is registered, we sent reset instructions. Check your inbox.", true);
    form.reset();
  } catch (err) {
    showMessage(err.message || "Could not send reset email.");
  }
});
