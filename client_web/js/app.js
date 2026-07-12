import { api } from "./api.js";
import { pullBootstrap, flushQueue } from "./sync.js";
import { router, setBottomNavActive, showTabPanels } from "./router.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderInvoices } from "./views/invoices.js";
import { renderCustomers } from "./views/customers.js";
import { renderSettings } from "./views/settings.js";

const gateScreen = document.getElementById("gate-screen");
const appScreen = document.getElementById("app-screen");
const gateMessage = document.getElementById("gate-message");
const guestStart = document.getElementById("guest-start");
const upgradeLink = document.getElementById("upgrade-link");
const signInLink = document.getElementById("sign-in-link");
const subscribeLink = document.getElementById("subscribe-link");
const syncStatus = document.getElementById("sync-status");
const bottomNav = document.getElementById("bottom-nav");
const fab = document.getElementById("fab");

const isLocal =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
if (isLocal) {
  const loginBase = "http://127.0.0.1:8080/account/login.html?next=pwa";
  const subBase = "http://127.0.0.1:8080/account/signup.html";
  const upgradeBase = "http://127.0.0.1:8080/account/subscribe.html?upgrade=1&tier=cloud";
  if (signInLink) signInLink.href = loginBase;
  if (subscribeLink) subscribeLink.href = subBase;
  if (upgradeLink) upgradeLink.href = upgradeBase;
}

const ctx = { isGuest: false, entitlements: null, onSyncStatus: setSyncStatus };

async function setSyncStatus(text) {
  if (!text) {
    syncStatus.hidden = true;
    return;
  }
  syncStatus.hidden = false;
  syncStatus.textContent = text;
}

function panelForTab(tab) {
  const map = { home: "home", invoices: "invoices", customers: "customers", settings: "settings" };
  return document.getElementById(`tab-${map[tab] || tab}`);
}

function handleAuthCallback() {
  const hash = window.location.hash || "";
  if (!hash.startsWith("#auth/callback")) return false;
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  const access = params.get("access_token");
  const refresh = params.get("refresh_token");
  if (!access) return false;
  localStorage.setItem("frogswork_access_token", access);
  if (refresh) localStorage.setItem("frogswork_refresh_token", refresh);
  localStorage.removeItem("frogswork_guest_token");
  history.replaceState(null, "", window.location.pathname + window.location.search);
  return true;
}

async function renderActive() {
  const tab = router.tab === "create" ? "invoices" : router.tab;
  setBottomNavActive(tab);
  showTabPanels(tab);
  fab.hidden = tab === "settings" || router.sub === "create" || router.sub === "preview";
  if (tab === "home") fab.hidden = true;
  if (tab === "invoices" && !router.sub) fab.hidden = false;
  fab.textContent = tab === "customers" ? "+" : tab === "invoices" ? "+" : "✎";
  fab.onclick = () => {
    if (tab === "invoices") router.navigate("invoices", "create");
    else if (tab === "customers") router.navigate("customers", "add");
    else if (tab === "settings") router.navigate("settings", "business");
  };

  const panel = panelForTab(tab);
  if (!panel) return;
  if (tab === "home") await renderDashboard(panel, ctx);
  else if (tab === "invoices") await renderInvoices(panel, ctx);
  else if (tab === "customers") await renderCustomers(panel, ctx);
  else if (tab === "settings") await renderSettings(panel, ctx);
}

async function showApp() {
  gateScreen.hidden = true;
  appScreen.hidden = false;
  bottomNav.hidden = false;
  router.navigate(router.tab || "home");
  await renderActive();
}

async function resolveAccess() {
  if (handleAuthCallback()) {
    gateMessage.textContent = "Signing in…";
  }
  ctx.isGuest = api.isGuest();
  const token = localStorage.getItem("frogswork_access_token");
  if (!token && !ctx.isGuest) {
    gateMessage.textContent = isLocal
      ? `Sign in on the web or try guest mode. API: ${api.getBase()}`
      : "Sign in with your Cloud account or try a guest workspace.";
    return;
  }
  if (ctx.isGuest) {
    try {
      await pullBootstrap();
      await flushQueue(setSyncStatus);
    } catch {
      /* offline */
    }
    await showApp();
    return;
  }
  try {
    ctx.entitlements = await api.entitlements();
    if (ctx.entitlements.storage_tier !== "cloud" || !ctx.entitlements.active) {
      gateMessage.textContent = "Mobile requires an active Cloud subscription.";
      upgradeLink.hidden = false;
      if (signInLink) signInLink.hidden = true;
      return;
    }
    await pullBootstrap();
    await flushQueue(setSyncStatus);
    await showApp();
  } catch (err) {
    gateMessage.textContent = `Showing cached data (${err.message}).`;
    await showApp();
  }
}

guestStart.addEventListener("click", async () => {
  gateMessage.textContent = "Starting guest trial…";
  try {
    const session = await api.guestSession();
    localStorage.setItem("frogswork_guest_token", session.guest_token);
    localStorage.removeItem("frogswork_access_token");
    ctx.isGuest = true;
    await pullBootstrap();
    gateMessage.textContent = "";
    await showApp();
  } catch (err) {
    gateMessage.textContent = err.message;
    gateMessage.className = "error-text";
  }
});

document.querySelectorAll("#bottom-nav button").forEach((btn) => {
  btn.addEventListener("click", () => router.navigate(btn.dataset.tab));
});

router.init();
router.onChange(() => renderActive());

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}

window.addEventListener("online", () => flushQueue(setSyncStatus));
resolveAccess();
