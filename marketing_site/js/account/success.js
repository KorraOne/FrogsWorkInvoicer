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
  const tierLabel = tier === "cloud" ? "Cloud" : tier === "local" ? "Local" : "";
  if (leadEl) {
    const who = email ? `Signed in as ${email}. ` : "";
    const plan = tierLabel ? `${tierLabel} plan is active. ` : "";
    leadEl.textContent = `${who}${plan}Download FrogsWork for Windows${tier === "cloud" ? " or open the browser app on your phone" : ""}.`;
  }
} else if (flow === "upgrade") {
  if (titleEl) titleEl.textContent = "Plan updated";
  if (leadEl) {
    leadEl.textContent =
      tier === "cloud"
        ? "Cloud is active. On your PC, open Settings to migrate data, then use the mobile app."
        : "Your plan was updated. Open FrogsWork on your PC.";
  }
}

if (tier === "local" && pwaLink) {
  pwaLink.hidden = true;
}

if (pwaLink) pwaLink.setAttribute("href", PWA_URL);
