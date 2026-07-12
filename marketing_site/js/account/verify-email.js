import { apiRequest } from "./api.js";

const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const statusEl = document.getElementById("verify-status");

async function run() {
  if (!token) {
    if (statusEl) statusEl.textContent = "Missing verification token.";
    return;
  }
  try {
    await apiRequest("POST", "/auth/verify-email", { token });
    if (statusEl) {
      statusEl.textContent = "Email verified. You can sign in and use FrogsWork.";
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = err.message || "Verification failed.";
  }
}

run();
