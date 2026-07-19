import "./styles/app.css";
import { fetchAccount } from "./api/mobile";
import { captureAuthFromUrl, clearSession, getAccessToken, mirrorSessionToDesktopHost } from "./auth/session";
import { openSheet, showToast } from "./components/ui";
import { cache } from "./data/idb";
import { pullBootstrap, flushQueue } from "./data/sync";
import {
  hasSeenBusinessSetupPrompt,
  isSetupBusinessComplete,
  markBusinessSetupPromptSeen,
} from "./domain/businessCompleteness";
import { applyHostEnvironment, watchPywebviewReady, wireExternalLinks } from "./lib/host";
import { initCloudAnalytics, trackEvent, trackScreen } from "./lib/analytics";
import { reportDeviceSighting } from "./lib/device";
import { allowNavigation, rememberAllowedHash, getLastAllowedHash } from "./lib/unsaved";
import { router, setBottomNavActive, showTabPanels } from "./router";
import { renderWelcome } from "./screens/welcome";
import { renderUpgrade } from "./screens/upgrade";
import { renderDashboard } from "./screens/dashboard";
import { renderCustomers } from "./screens/customers";
import { renderInvoices } from "./screens/invoices";
import { renderQuotes } from "./screens/quotes";
import { renderSettings } from "./screens/settings";
import type { AppContext, MobileAccount, Screen } from "./types";

applyHostEnvironment();
watchPywebviewReady();
wireExternalLinks(document);
mirrorSessionToDesktopHost();
window.addEventListener("pywebviewready", () => mirrorSessionToDesktopHost());

if (/^\/\/+/.test(window.location.pathname)) {
  history.replaceState(null, "", "/" + window.location.search + window.location.hash);
}

const root = document.getElementById("app") as HTMLElement;
const bottomNav = document.getElementById("bottom-nav") as HTMLElement;
const fab = document.getElementById("fab") as HTMLButtonElement;
const syncStatus = document.getElementById("sync-status") as HTMLElement;

let screen: Screen = "welcome";
let rendering = false;
const ctx: AppContext = {
  account: null,
  onSyncStatus: (text) => {
    if (!text) {
      syncStatus.hidden = true;
      return;
    }
    syncStatus.hidden = false;
    syncStatus.textContent = text;
  },
};

function showChrome(visible: boolean) {
  bottomNav.hidden = !visible;
  fab.hidden = !visible;
  const header = document.querySelector(".app-header") as HTMLElement | null;
  if (header) header.hidden = !visible;
  if (!visible) document.body.classList.remove("app-flow-immersive");
}

function setScreen(next: Screen) {
  screen = next;
  showChrome(next === "app");
}

const BANNER_ASPECT = 1.65;
const FALLBACK_BRAND_NAME = "FrogsWork\nInvoicer";

function toDataUrl(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  return value.startsWith("data:") ? value : `data:image/png;base64,${value}`;
}

function loadImageSize(src: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth || 1, height: img.naturalHeight || 1 });
    img.onerror = () => reject(new Error("logo load failed"));
    img.src = src;
  });
}

async function refreshNavAccount(): Promise<void> {
  const brandEl = document.getElementById("nav-brand");
  const avatarEl = document.getElementById("nav-avatar");
  const nameEl = document.getElementById("nav-brand-name");
  if (!brandEl || !avatarEl || !nameEl) return;

  let businessName = "";
  let logoRaw = "";
  try {
    const settings = await cache.getSettings();
    const businesses = await cache.getBusinesses();
    const defaultName = String(settings.default_business || Object.keys(businesses)[0] || "");
    const profile =
      ((defaultName && businesses[defaultName]) as Record<string, unknown> | undefined) ||
      (Object.values(businesses)[0] as Record<string, unknown> | undefined);
    if (profile) {
      businessName = String(profile.business_name || defaultName || "").trim();
      // Prefer original upload (no invoice-header placement bake).
      logoRaw = String(profile.logo_source_b64 || profile.logo_b64 || "").trim();
    }
  } catch {
    businessName = "";
    logoRaw = "";
  }

  const displayName = businessName || FALLBACK_BRAND_NAME;
  nameEl.textContent = displayName;
  brandEl.classList.remove("app-nav-brand--banner", "app-nav-brand--avatar");

  if (!logoRaw) {
    brandEl.classList.add("app-nav-brand--avatar");
    avatarEl.hidden = false;
    nameEl.hidden = false;
    avatarEl.innerHTML = `<img class="app-nav-brand-fallback" src="/icons/icon-192.png" alt="">`;
    return;
  }

  const src = toDataUrl(logoRaw);
  try {
    const size = await loadImageSize(src);
    const aspect = size.width / size.height;
    if (aspect >= BANNER_ASPECT) {
      brandEl.classList.add("app-nav-brand--banner");
      avatarEl.hidden = false;
      nameEl.hidden = true;
      avatarEl.innerHTML = `<img src="${src}" alt="">`;
      return;
    }
  } catch {
    // Fall through to centered avatar treatment.
  }

  brandEl.classList.add("app-nav-brand--avatar");
  avatarEl.hidden = false;
  nameEl.hidden = false;
  avatarEl.innerHTML = `<img src="${src}" alt="">`;
}

function showWelcome(message?: string, isError = false) {
  setScreen("welcome");
  renderWelcome(root, {
    message,
    isError,
    onSuccess: (account) => {
      ctx.account = account;
      if (account.active) {
        enterApp();
      } else {
        setScreen("upgrade");
        renderUpgrade(root, account, () => showWelcome("Signed out."));
      }
    },
  });
}

function showUpgrade(account: MobileAccount) {
  setScreen("upgrade");
  ctx.account = account;
  renderUpgrade(root, account, () => showWelcome("Signed out."));
}

async function maybePromptBusinessSetup() {
  const accountKey = String(ctx.account?.email || "")
    .trim()
    .toLowerCase();
  if (!accountKey || hasSeenBusinessSetupPrompt(accountKey)) return;

  const [businesses, settings] = await Promise.all([cache.getBusinesses(), cache.getSettings()]);
  if (isSetupBusinessComplete(businesses, settings)) {
    markBusinessSetupPromptSeen(accountKey);
    return;
  }

  const action = await openSheet({
    title: "Set up your business",
    bodyHtml: `<p class="hint">Add your business details so they appear on invoices. You can skip and finish this later from Settings.</p>`,
    actions: [
      { id: "skip", label: "Skip for now", className: "btn secondary" },
      { id: "setup", label: "Set up business", className: "btn primary" },
    ],
  });
  markBusinessSetupPromptSeen(accountKey);
  if (action === "setup") {
    router.navigate("settings", "business");
  }
}

async function enterApp() {
  setScreen("app");
  root.innerHTML = `
    <div id="tab-home" class="tab-panel" data-tab="home"></div>
    <div id="tab-quotes" class="tab-panel" data-tab="quotes" hidden></div>
    <div id="tab-invoices" class="tab-panel" data-tab="invoices" hidden></div>
    <div id="tab-customers" class="tab-panel" data-tab="customers" hidden></div>
    <div id="tab-settings" class="tab-panel" data-tab="settings" hidden></div>`;
  await pullBootstrap();
  const settings = await cache.getSettings();
  updateQuotesNavVisibility(settings);
  await refreshNavAccount();
  void reportDeviceSighting();
  trackEvent("login", { method: "session" });
  const flush = await flushQueue(ctx.onSyncStatus);
  if (!flush.ok) {
    showToast(flush.error || "Some changes could not sync. Will retry when online.", "error");
  }
  rememberAllowedHash(location.hash || "#home");
  router.navigate(router.tab || "home");
  await renderActive();
  await maybePromptBusinessSetup();
}

function updateQuotesNavVisibility(settings: Record<string, unknown>) {
  const enabled = Boolean(settings.quotes_enabled);
  const nav = document.getElementById("nav-quotes") as HTMLElement | null;
  if (nav) nav.hidden = !enabled;
  return enabled;
}

async function renderActive() {
  const settings = await cache.getSettings();
  const quotesEnabled = updateQuotesNavVisibility(settings);
  if (router.tab === "quotes" && !quotesEnabled) {
    showToast("Enable Quotes in Settings → General.", "error");
    router.tab = "home";
    router.sub = null;
    router.params = {};
    history.replaceState(null, "", "#home");
    rememberAllowedHash("#home");
  }

  const tab = router.tab === "create" ? "invoices" : router.tab;
  setBottomNavActive(tab);
  showTabPanels(tab);

  const immersive =
    (tab === "invoices" || tab === "quotes") &&
    (router.sub === "create" || router.sub === "success");
  if (screen === "app") {
    bottomNav.hidden = immersive;
    document.body.classList.toggle("app-flow-immersive", immersive);
  }

  fab.hidden =
    immersive ||
    tab === "settings" ||
    Boolean(router.sub) ||
    tab === "home";
  if (tab === "invoices" && !router.sub) fab.hidden = false;
  if (tab === "quotes" && !router.sub) fab.hidden = false;
  if (tab === "customers" && !router.sub) fab.hidden = false;
  fab.textContent = "+";
  fab.setAttribute(
    "aria-label",
    tab === "customers" ? "Add customer" : tab === "quotes" ? "Create quote" : "Create invoice"
  );
  fab.onclick = () => {
    if (tab === "invoices") router.navigate("invoices", "create");
    else if (tab === "quotes") router.navigate("quotes", "create");
    else if (tab === "customers") router.navigate("customers", "add");
  };

  const panel = document.getElementById(`tab-${tab}`) as HTMLElement;
  if (!panel) return;
  if (tab === "home") await renderDashboard(panel, ctx);
  else if (tab === "quotes") await renderQuotes(panel, ctx);
  else if (tab === "invoices") await renderInvoices(panel, ctx);
  else if (tab === "customers") await renderCustomers(panel, ctx);
  else if (tab === "settings") await renderSettings(panel, ctx);

  const screenName = router.sub ? `${tab}_${router.sub}` : tab;
  trackScreen(screenName);
  if (tab === "settings") trackEvent("open_settings");
  if (tab === "invoices" && router.sub === "create") trackEvent("create_invoice_start");
  if (tab === "quotes" && router.sub === "create") trackEvent("create_quote_start");

  if (tab === "settings" || tab === "home") {
    void refreshNavAccount();
  }
}

async function boot() {
  await captureAuthFromUrl();
  initCloudAnalytics();

  const token = getAccessToken();
  if (!token) {
    showWelcome();
    return;
  }
  try {
    const account = await fetchAccount();
    ctx.account = account;
    if (account.active) {
      await enterApp();
    } else {
      showUpgrade(account);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Could not start app.";
    if (msg.toLowerCase().includes("unauthorized") || msg.includes("401")) {
      clearSession();
      showWelcome("Session expired. Sign in again.", true);
    } else {
      showWelcome(msg, true);
    }
  }
}

document.querySelectorAll("#bottom-nav [data-tab]").forEach((btn) => {
  btn.addEventListener("click", async (e) => {
    e.preventDefault();
    const next = (btn as HTMLButtonElement).dataset.tab || "home";
    if (!(await allowNavigation())) return;
    router.navigate(next);
  });
});

document.getElementById("nav-settings-btn")?.addEventListener("click", async (e) => {
  e.preventDefault();
  if (!(await allowNavigation())) return;
  router.navigate("settings");
});

document.getElementById("nav-sign-out")?.addEventListener("click", async (e) => {
  e.preventDefault();
  if (!(await allowNavigation())) return;
  clearSession();
  location.reload();
});

router.init();
router.onChange(() => {
  if (screen !== "app") return;
  if (rendering) return;
  rendering = true;
  (async () => {
    try {
      const targetHash = location.hash || "#home";
      if (targetHash !== getLastAllowedHash()) {
        if (!(await allowNavigation())) {
          const restore = getLastAllowedHash();
          if (location.hash !== restore) {
            history.replaceState(null, "", restore || "#home");
            router.parseHash();
          }
          return;
        }
      }
      rememberAllowedHash(location.hash || "#home");
      await renderActive();
    } catch (err) {
      showWelcome(err instanceof Error ? err.message : "Error", true);
    } finally {
      rendering = false;
    }
  })();
});

window.addEventListener("online", () => flushQueue(ctx.onSyncStatus));

boot().catch((err) => showWelcome(err.message, true));
