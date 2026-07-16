import "./styles/app.css";
import { fetchAccount } from "./api/mobile";
import { captureAuthFromUrl, clearSession, getAccessToken, saveSession } from "./auth/session";
import { showToast } from "./components/ui";
import { pullBootstrap, flushQueue } from "./data/sync";
import { applyHostEnvironment, wireExternalLinks } from "./lib/host";
import { allowNavigation, rememberAllowedHash, getLastAllowedHash } from "./lib/unsaved";
import { router, setBottomNavActive, showTabPanels } from "./router";
import { renderWelcome } from "./screens/welcome";
import { renderUpgrade } from "./screens/upgrade";
import { renderDashboard } from "./screens/dashboard";
import { renderCustomers } from "./screens/customers";
import { renderInvoices } from "./screens/invoices";
import { renderSettings } from "./screens/settings";
import type { AppContext, MobileAccount, Screen } from "./types";

applyHostEnvironment();
wireExternalLinks(document);

if (/^\/\/+/.test(window.location.pathname)) {
  history.replaceState(null, "", "/" + window.location.search + window.location.hash);
}

captureAuthFromUrl();

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

function showWelcome(message?: string, isError = false) {
  setScreen("welcome");
  renderWelcome(root, {
    message,
    isError,
    onSuccess: (account) => {
      ctx.account = account;
      if (account.storage_tier === "cloud" && account.active) {
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

async function enterApp() {
  setScreen("app");
  root.innerHTML = `
    <div id="tab-home" class="tab-panel" data-tab="home"></div>
    <div id="tab-invoices" class="tab-panel" data-tab="invoices" hidden></div>
    <div id="tab-customers" class="tab-panel" data-tab="customers" hidden></div>
    <div id="tab-settings" class="tab-panel" data-tab="settings" hidden></div>`;
  await pullBootstrap();
  const flush = await flushQueue(ctx.onSyncStatus);
  if (!flush.ok) {
    showToast(flush.error || "Some changes could not sync. Will retry when online.", "error");
  }
  rememberAllowedHash(location.hash || "#home");
  router.navigate(router.tab || "home");
  await renderActive();
}

async function renderActive() {
  const tab = router.tab === "create" ? "invoices" : router.tab;
  setBottomNavActive(tab);
  showTabPanels(tab);

  const immersive =
    tab === "invoices" &&
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
  if (tab === "customers" && !router.sub) fab.hidden = false;
  fab.textContent = "+";
  fab.setAttribute("aria-label", tab === "customers" ? "Add customer" : "Create invoice");
  fab.onclick = () => {
    if (tab === "invoices") router.navigate("invoices", "create");
    else if (tab === "customers") router.navigate("customers", "add");
  };

  const panel = document.getElementById(`tab-${tab}`) as HTMLElement;
  if (!panel) return;
  if (tab === "home") await renderDashboard(panel, ctx);
  else if (tab === "invoices") await renderInvoices(panel, ctx);
  else if (tab === "customers") await renderCustomers(panel, ctx);
  else if (tab === "settings") await renderSettings(panel, ctx);
}

async function boot() {
  const token = getAccessToken();
  if (!token) {
    showWelcome();
    return;
  }
  try {
    const account = await fetchAccount();
    ctx.account = account;
    if (account.storage_tier === "cloud" && account.active) {
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

document.querySelectorAll("#bottom-nav button").forEach((btn) => {
  btn.addEventListener("click", async (e) => {
    e.preventDefault();
    const next = (btn as HTMLButtonElement).dataset.tab || "home";
    if (!(await allowNavigation())) return;
    router.navigate(next);
  });
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
