import { esc } from "../lib/escape";
import { clearSession } from "../auth/session";
import type { MobileAccount } from "../types";

const upgradeUrl = "https://frogswork.com/account/subscribe.html?upgrade=1&tier=cloud";

export function renderUpgrade(
  root: HTMLElement,
  account: MobileAccount,
  onSignOut: () => void
) {
  const localActive = account.storage_tier === "local" && account.active;
  const title = localActive ? "Upgrade to Cloud" : "Subscription required";
  const lead = localActive
    ? "Your Local plan includes data on one PC. Upgrade to Cloud to use this app and sync your data."
    : account.active
      ? "An active Cloud subscription is required to use this app."
      : "Your subscription is inactive. Renew or upgrade to Cloud to use this app.";

  root.innerHTML = `
    <div class="gate-screen">
      <div class="gate-brand gate-brand-compact">
        <img class="gate-logo gate-logo-sm" src="/icons/splash-logo.png" alt="FrogsWork" width="64" height="64">
        <p class="gate-tagline">Sales invoicing for Australian sole traders</p>
      </div>
      <section class="panel upgrade-panel gate-card">
        <h2>${esc(title)}</h2>
        <p class="upgrade-signed-in">Signed in as ${esc(account.email)}</p>
        <p class="hint">${esc(lead)}</p>
        <ul class="upgrade-list">
          <li><strong>Local</strong> (deferred): data stays on one PC</li>
          <li><strong>Cloud</strong>: browser, phone, and desktop with sync</li>
        </ul>
        <div class="btn-row stacked">
          <a class="btn primary btn-block" href="${upgradeUrl}">${localActive ? "Upgrade to Cloud" : "Subscribe to Cloud"}</a>
          ${
            account.portal_url && !account.active
              ? `<a class="btn secondary btn-block" href="${esc(account.portal_url)}" target="_blank" rel="noopener">Manage subscription</a>`
              : ""
          }
        </div>
        <button type="button" id="upgrade-sign-out" class="btn ghost">Use a different account</button>
      </section>
      <footer class="gate-footer">
        <a href="https://korraone.com" target="_blank" rel="noopener">KorraOne</a>
        ·
        <a href="https://frogswork.com" target="_blank" rel="noopener">frogswork.com</a>
      </footer>
    </div>`;

  root.querySelector("#upgrade-sign-out")?.addEventListener("click", () => {
    clearSession();
    onSignOut();
  });
}
