import { PWA_URL } from "./config.js";

const params = new URLSearchParams(location.search);
const flow = params.get("flow") || "login";
const email = params.get("email") || "";
const tier = params.get("tier") || "";

const titleEl = document.getElementById("success-title");
const leadEl = document.getElementById("success-lead");
const pwaLink = document.getElementById("open-pwa");

if (flow === "subscribe" || flow === "register") {
  if (titleEl) titleEl.textContent = "Subscription active";
  if (leadEl) {
    const who = email ? `Signed in as ${email}. ` : "";
    leadEl.textContent = `${who}Open the Cloud app to start invoicing. Optional: install the Windows shell from Download.`;
  }
} else if (flow === "upgrade") {
  if (titleEl) titleEl.textContent = "Plan updated";
  if (leadEl) {
    leadEl.textContent = "Cloud is active. Open the app to continue.";
  }
} else if (flow === "login") {
  if (titleEl) titleEl.textContent = "Signed in";
  if (leadEl) {
    leadEl.textContent = "Open the Cloud app to continue.";
  }
}

if (pwaLink) pwaLink.setAttribute("href", PWA_URL);
