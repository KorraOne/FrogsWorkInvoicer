import { esc } from "../lib/escape";
import { clearSession } from "../auth/session";
import type { MobileAccount } from "../types";

const subscribeUrl = "https://frogswork.com/account/subscribe.html";

export function renderUpgrade(
  root: HTMLElement,
  account: MobileAccount,
  onSignOut: () => void
) {
  root.innerHTML = `
    <div class="gate-screen">
      <div class="gate-brand gate-brand-compact">
        <img class="gate-logo gate-logo-sm" src="/icons/splash-logo.png" alt="FrogsWork" width="64" height="64">
        <p class="gate-tagline">Sales invoicing for Australian sole traders</p>
      </div>
      <section class="panel upgrade-panel gate-card">
        <h2>Subscription required</h2>
        <p class="upgrade-signed-in">Signed in as ${esc(account.email)}</p>
        <p class="hint">Your FrogsWork subscription is inactive. Subscribe or renew to use this app.</p>
        <div class="btn-row stacked">
          <a class="btn primary btn-block" href="${subscribeUrl}">Subscribe</a>
          ${
            account.portal_url
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
