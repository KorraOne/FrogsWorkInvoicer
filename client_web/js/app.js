import { api } from "./api.js";
import { pullBootstrap, flushQueue } from "./sync.js";
import { router, setBottomNavActive, showTabPanels } from "./router.js";

function captureAuthFromUrl() {
  let access = "";
  let refresh = "";

  const hash = window.location.hash || "";
  if (hash.startsWith("#auth/callback")) {
    const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
    const params = new URLSearchParams(query);
    access = params.get("access_token") || "";
    refresh = params.get("refresh_token") || "";
  }

  const search = new URLSearchParams(window.location.search);
  if (search.get("pwa_auth") === "1") {
    access = access || search.get("access_token") || "";
    refresh = refresh || search.get("refresh_token") || "";
  }

  if (!access) return false;

  api.saveSession({ access_token: access, refresh_token: refresh || undefined });
  const path = window.location.pathname.replace(/^\/+/, "/") || "/";
  history.replaceState(null, "", path);
  return true;
}

if (/^\/\/+/.test(window.location.pathname)) {
  history.replaceState(null, "", "/" + window.location.search + window.location.hash);
}

const authJustCaptured = captureAuthFromUrl();

const gateScreen = document.getElementById("gate-screen");
const upgradeScreen = document.getElementById("upgrade-screen");
const appScreen = document.getElementById("app-screen");
const gateMessage = document.getElementById("gate-message");
const gateLoginSubmit = document.getElementById("gate-login-submit");
const upgradeTitle = document.getElementById("upgrade-title");
const upgradeSignedIn = document.getElementById("upgrade-signed-in");
const upgradeLead = document.getElementById("upgrade-lead");
const upgradeCta = document.getElementById("upgrade-cta");
const upgradePortal = document.getElementById("upgrade-portal");
const upgradeSignOut = document.getElementById("upgrade-sign-out");
const signInWebLink = document.getElementById("sign-in-web-link");
const subscribeLink = document.getElementById("subscribe-link");
const resetSession = document.getElementById("reset-session");
const syncStatus = document.getElementById("sync-status");
const bottomNav = document.getElementById("bottom-nav");
const fab = document.getElementById("fab");

const isLocal =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const upgradeUrl = isLocal
  ? "http://127.0.0.1:8080/account/subscribe.html?upgrade=1&tier=cloud"
  : "https://frogswork.com/account/subscribe.html?upgrade=1&tier=cloud";

if (isLocal) {
  const loginBase = "http://127.0.0.1:8080/account/login.html?next=pwa";
  const subBase = "http://127.0.0.1:8080/account/signup.html";
  if (signInWebLink) signInWebLink.href = loginBase;
  if (subscribeLink) subscribeLink.href = subBase;
}
if (upgradeCta) upgradeCta.href = upgradeUrl;

const ctx = { entitlements: null, onSyncStatus: setSyncStatus };

function clearStoredSession() {
  api.clearSession();
  ctx.entitlements = null;
}

function hideAllScreens() {
  gateScreen.hidden = true;
  upgradeScreen.hidden = true;
  appScreen.hidden = true;
  bottomNav.hidden = true;
  fab.hidden = true;
}

function showWelcomeGate(message, { isError = false } = {}) {
  hideAllScreens();
  gateScreen.hidden = false;
  gateMessage.textContent = message;
  gateMessage.className = isError ? "error-text" : "hint";
}

function showUpgradeGate(entitlements) {
  hideAllScreens();
  upgradeScreen.hidden = false;

  const email = entitlements?.email || "";
  const localActive = entitlements?.storage_tier === "local" && entitlements?.active;
  const inactive = !entitlements?.active;

  if (upgradeTitle) {
    upgradeTitle.textContent = localActive ? "Upgrade to Cloud" : "Subscription required";
  }
  if (upgradeSignedIn) {
    upgradeSignedIn.textContent = email ? `Signed in as ${email}` : "You're signed in.";
  }
  if (upgradeLead) {
    if (localActive) {
      upgradeLead.textContent =
        "Your Local plan includes the full desktop app. Upgrade to Cloud to use this mobile app and sync your data.";
    } else if (inactive) {
      upgradeLead.textContent =
        "Your subscription is inactive. Renew or upgrade to Cloud to use the mobile app.";
    } else {
      upgradeLead.textContent = "An active Cloud subscription is required to use the mobile app.";
    }
  }
  if (upgradeCta) {
    upgradeCta.textContent = localActive ? "Upgrade to Cloud" : "Subscribe to Cloud";
    upgradeCta.href = upgradeUrl;
  }
  if (upgradePortal) {
    const portalUrl = entitlements?.portal_url || "";
    if (portalUrl && inactive) {
      upgradePortal.href = portalUrl;
      upgradePortal.hidden = false;
    } else {
      upgradePortal.hidden = true;
    }
  }
}

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

  if (tab === "home") {
    const { renderDashboard } = await import("./views/dashboard.js");
    await renderDashboard(panel, ctx);
  } else if (tab === "invoices") {
    const { renderInvoices } = await import("./views/invoices.js");
    await renderInvoices(panel, ctx);
  } else if (tab === "customers") {
    const { renderCustomers } = await import("./views/customers.js");
    await renderCustomers(panel, ctx);
  } else if (tab === "settings") {
    const { renderSettings } = await import("./views/settings.js");
    await renderSettings(panel, ctx);
  }
}

async function showApp() {
  hideAllScreens();
  appScreen.hidden = false;
  bottomNav.hidden = false;
  router.navigate(router.tab || "home");
  await renderActive();
}

async function resolveAccess() {
  if (authJustCaptured) {
    showWelcomeGate("Signing in…");
  }
  const token = localStorage.getItem("frogswork_access_token");
  if (!token) {
    showWelcomeGate(
      isLocal
        ? `Sign in with your Cloud subscription. API: ${api.getBase()}`
        : "Sign in with your Cloud subscription to use the mobile app."
    );
    return;
  }
  try {
    ctx.entitlements = await api.entitlements();
    if (ctx.entitlements.storage_tier !== "cloud" || !ctx.entitlements.active) {
      showUpgradeGate(ctx.entitlements);
      return;
    }
    await pullBootstrap();
    await flushQueue(setSyncStatus);
    await showApp();
  } catch (err) {
    const msg = String(err.message || "");
    if (msg.includes("401") || msg.toLowerCase().includes("unauthorized")) {
      clearStoredSession();
      showWelcomeGate("Session expired. Sign in again.", { isError: true });
      return;
    }
    showWelcomeGate(`Could not verify account (${msg}). Sign in again.`, { isError: true });
  }
}

async function handleGateLogin() {
  const email = document.getElementById("gate-email")?.value?.trim() || "";
  const password = document.getElementById("gate-password")?.value || "";

  if (!email || !password) {
    showWelcomeGate("Enter your email and password.", { isError: true });
    return;
  }

  if (gateLoginSubmit) gateLoginSubmit.disabled = true;
  showWelcomeGate("Signing in…");

  try {
    const tokens = await api.login(email, password);
    api.saveSession(tokens);
    await resolveAccess();
  } catch (err) {
    showWelcomeGate(api.mapLoginError(err.message), { isError: true });
  } finally {
    if (gateLoginSubmit) gateLoginSubmit.disabled = false;
  }
}

function signOutToWelcome() {
  clearStoredSession();
  const emailInput = document.getElementById("gate-email");
  const passwordInput = document.getElementById("gate-password");
  if (emailInput) emailInput.value = "";
  if (passwordInput) passwordInput.value = "";
  showWelcomeGate("Signed out. Sign in with your Cloud subscription.");
}

gateLoginSubmit?.addEventListener("click", handleGateLogin);
document.getElementById("gate-login-form")?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    handleGateLogin();
  }
});
resetSession?.addEventListener("click", signOutToWelcome);
upgradeSignOut?.addEventListener("click", signOutToWelcome);

document.querySelectorAll("#bottom-nav button").forEach((btn) => {
  btn.addEventListener("click", () => router.navigate(btn.dataset.tab));
});

router.init();
router.onChange(() => {
  if (!appScreen.hidden) {
    renderActive().catch((err) => {
      showWelcomeGate(err.message || "Could not open this screen.", { isError: true });
    });
  }
});

window.addEventListener("online", () => flushQueue(setSyncStatus));

resolveAccess().catch((err) => {
  showWelcomeGate(err.message || "Could not start app.", { isError: true });
});
