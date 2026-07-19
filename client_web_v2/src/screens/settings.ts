import {
  deleteAccount,
  deleteAccountData,
  downloadAccountExport,
  downloadTaxExport,
  fetchAccount,
  resendVerification,
} from "../api/mobile";
import {
  bankFieldsHtml,
  businessAddressFieldsHtml,
  dueRuleFieldsHtml,
  gstFieldsHtml,
  wireDueRuleToggles,
} from "../components/forms";
import {
  bakeLogoToHeaderSlot,
  logoEditorHtml,
  readLogoStateFromRecord,
  refreshLogoEditorSection,
  wireLogoEditor,
  type LogoEditorState,
} from "../components/logoEditor";
import { showToast } from "../components/ui";
import { cache } from "../data/idb";
import { clearSession } from "../auth/session";
import {
  flushQueue,
  pullBootstrap,
  upsertBusiness,
  upsertSettings,
} from "../data/sync";
import { listAuFinancialYearOptions } from "../domain/taxExport";
import {
  formatAddressMultiline,
  normalizeAbn,
  normalizeAccountNumber,
  normalizeAuAddress,
  normalizeBsb,
  readAddressFromForm,
} from "../domain/address";
import { dueRuleFromFormData, dueRuleFromSettings } from "../domain/dueDates";
import { parseGstRegisteredForm, validateBusinessGstSettings } from "../domain/gst";
import { esc } from "../lib/escape";
import { attachUnsavedGuard, clearLeaveGuard } from "../lib/unsaved";
import { router } from "../router";
import type { AppContext } from "../types";

const SUPPORT_HUB_URL = "https://frogswork.com/support.html";
const SUPPORT_ISSUES_URL = "https://frogswork.com/issues.html";
const SUPPORT_GUIDES_URL = "https://frogswork.com/guides.html";
const SUPPORT_CONTACT_URL = "https://frogswork.com/contact.html";

export async function renderSettings(panel: HTMLElement, ctx: AppContext) {
  clearLeaveGuard();
  if (
    router.sub === "business" ||
    router.sub === "business-edit" ||
    router.sub === "business-add"
  ) {
    return renderBusiness(panel, ctx);
  }
  if (router.sub === "general") return renderGeneralHub(panel);
  if (router.sub === "payment-terms") return renderPaymentTerms(panel, ctx);
  if (router.sub === "email-sending") return renderEmailSending(panel, ctx);
  if (router.sub === "account" || router.sub === "sync") return renderAccount(panel, ctx);
  if (router.sub === "help") return renderHelp(panel);

  panel.innerHTML = `
    <h2 class="section-title">Settings</h2>
    <a class="nav-card" href="#settings/business">
      <span class="nav-card-title">Business details</span>
      <span class="nav-card-hint">Shown on your invoices</span>
    </a>
    <a class="nav-card" href="#settings/general">
      <span class="nav-card-title">General</span>
      <span class="nav-card-hint">Payment terms, email, and quotes</span>
    </a>
    <a class="nav-card" href="#settings/account">
      <span class="nav-card-title">Account</span>
      <span class="nav-card-hint">Subscription, sync, and sign out</span>
    </a>
    <a class="nav-card" href="#settings/help">
      <span class="nav-card-title">Help &amp; support</span>
      <span class="nav-card-hint">Guides, troubleshooting, and contact</span>
    </a>`;
}

async function renderGeneralHub(panel: HTMLElement) {
  const settings = await cache.getSettings();
  const quotesEnabled = Boolean(settings.quotes_enabled);
  panel.innerHTML = `
    <h2 class="section-title">General</h2>
    <a class="nav-card" href="#settings/payment-terms">
      <span class="nav-card-title">Payment terms</span>
      <span class="nav-card-hint">Default due date for new invoices</span>
    </a>
    <a class="nav-card" href="#settings/email-sending">
      <span class="nav-card-title">Email sending</span>
      <span class="nav-card-hint">CC, BCC, or no copy to you</span>
    </a>
    <section class="panel" style="margin-top:0.75rem">
      <h3 class="settings-subhead" style="margin-top:0">Quotes</h3>
      <p class="hint">Show a Quotes tab for quotes and price estimates. Off by default.</p>
      <label class="checkbox">
        <input type="checkbox" id="quotes-enabled" ${quotesEnabled ? "checked" : ""}>
        Enable quotes
      </label>
    </section>
    <button type="button" class="btn secondary" id="back-settings">Back</button>`;
  panel.querySelector("#back-settings")?.addEventListener("click", () =>
    router.navigate("settings")
  );
  panel.querySelector("#quotes-enabled")?.addEventListener("change", async (e) => {
    const checked = (e.target as HTMLInputElement).checked;
    try {
      await upsertSettings({ quotes_enabled: checked });
      const nav = document.getElementById("nav-quotes") as HTMLElement | null;
      if (nav) nav.hidden = !checked;
      showToast(checked ? "Quotes enabled." : "Quotes hidden.", "success");
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Could not save.", "error");
      (e.target as HTMLInputElement).checked = !checked;
    }
  });
}

function renderHelp(panel: HTMLElement) {
  panel.innerHTML = `
    <h2 class="section-title">Help &amp; support</h2>
    <p class="hint">Same resources as <a href="${SUPPORT_HUB_URL}" target="_blank" rel="noopener">frogswork.com/support</a>.</p>
    <p class="hint">To send quotes or price estimates, turn on <strong>Enable quotes</strong> under Settings → General.</p>
    <a class="nav-card" href="${SUPPORT_ISSUES_URL}" target="_blank" rel="noopener">
      <span class="nav-card-title">Frequent issues</span>
      <span class="nav-card-hint">Install, sign-in, sync, and WebView2</span>
    </a>
    <a class="nav-card" href="${SUPPORT_GUIDES_URL}" target="_blank" rel="noopener">
      <span class="nav-card-title">Video guides</span>
      <span class="nav-card-hint">Short clips for setup and invoicing</span>
    </a>
    <a class="nav-card" href="${SUPPORT_CONTACT_URL}" target="_blank" rel="noopener">
      <span class="nav-card-title">Contact support</span>
      <span class="nav-card-hint">Email us if you are still stuck</span>
    </a>
    <a class="nav-card" href="${SUPPORT_HUB_URL}" target="_blank" rel="noopener">
      <span class="nav-card-title">Support hub</span>
      <span class="nav-card-hint">Open the full support page</span>
    </a>
    <button type="button" class="btn secondary" id="back-settings">Back</button>`;
  panel.querySelector("#back-settings")?.addEventListener("click", () =>
    router.navigate("settings")
  );
}

async function renderAccount(panel: HTMLElement, ctx: AppContext) {
  const acc = ctx.account;
  const lastSync = localStorage.getItem("frogswork_last_sync");
  const businesses = await cache.getBusinesses();
  const bizNames = Object.keys(businesses).sort();
  const fyOptions = listAuFinancialYearOptions();
  const defaultFy = fyOptions[0]?.token || "";

  panel.innerHTML = `
    <section class="panel">
      <h2>Account</h2>
      <div class="preview-row"><span class="preview-label">Email</span><span>${esc(acc?.email || "")}</span></div>
      <div class="preview-row"><span class="preview-label">Subscription</span><span>${acc?.active ? "Active" : "Inactive"}</span></div>

      <h3 class="settings-subhead">Subscription</h3>
      <p class="hint">Cancel, change plan, or update billing in Stripe. FrogsWork opens the secure Customer Portal.</p>
      ${
        acc?.portal_url
          ? `<a class="btn secondary" href="${esc(acc.portal_url)}" target="_blank" rel="noopener">Manage subscription</a>`
          : `<p class="hint">Subscription portal unavailable. Contact support if you need billing help.</p>`
      }
      ${
        acc && !acc.email_verified
          ? `<button type="button" class="btn small secondary" id="resend-verify" style="margin-top:0.5rem">Resend verification</button>`
          : ""
      }

      <h3 class="settings-subhead">Your data</h3>
      <p class="hint">Download a ZIP of your Cloud data (JSON + invoice/quote PDFs) for your own records. FrogsWork cannot restore an export into your account later.</p>
      <div class="btn-row">
        <button type="button" class="btn secondary" id="export-data">Download my data</button>
      </div>

      <h3 class="settings-subhead">Tax time export</h3>
      <p class="hint">Income ledger CSV plus matching tax invoice PDFs for your accountant (Australian financial year). Separate from the full backup above.</p>
      <div class="field"><label>Financial year</label>
        <select id="tax-fy">
          ${fyOptions
            .map(
              (fy) =>
                `<option value="${esc(fy.token)}" ${fy.token === defaultFy ? "selected" : ""}>${esc(fy.display)}</option>`
            )
            .join("")}
        </select>
      </div>
      ${
        bizNames.length > 1
          ? `<div class="field"><label>Business</label>
              <select id="tax-business">
                <option value="">All businesses</option>
                ${bizNames.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")}
              </select>
            </div>`
          : ""
      }
      <div class="btn-row">
        <button type="button" class="btn secondary" id="tax-export">Download tax pack</button>
      </div>

      <p class="hint" style="margin-top:0.75rem">Delete all businesses, customers, invoices, and PDFs from FrogsWork Cloud. Your login and subscription stay. This cannot be undone and cannot be restored.</p>
      <button type="button" class="btn danger" id="wipe-data">Delete all my data</button>

      <h3 class="settings-subhead">Close account</h3>
      <p class="hint">Cancels your Stripe subscription immediately and permanently erases your FrogsWork Cloud account and data. This cannot be undone and cannot be restored.</p>
      <button type="button" class="btn danger" id="delete-account">Delete account</button>

      <div class="nav-card card-static" style="margin-top:1.25rem">
        <span class="nav-card-title">Sync</span>
        <span class="nav-card-hint">${lastSync ? `Last sync: ${new Date(lastSync).toLocaleString()}` : "Not synced yet"}</span>
        <button type="button" class="btn small secondary" id="sync-now">Sync now</button>
      </div>
      <div class="btn-row" style="margin-top:1rem">
        <button type="button" class="btn secondary" id="sign-out">Sign out</button>
        <button type="button" class="btn secondary" id="back-settings">Back</button>
      </div>
    </section>`;

  panel.querySelector("#back-settings")?.addEventListener("click", () =>
    router.navigate("settings")
  );
  panel.querySelector("#sync-now")?.addEventListener("click", async () => {
    try {
      await pullBootstrap();
      await flushQueue(ctx.onSyncStatus);
      showToast("Synced.", "success");
      await renderAccount(panel, ctx);
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Sync failed.", "error");
    }
  });
  panel.querySelector("#sign-out")?.addEventListener("click", () => {
    clearSession();
    location.reload();
  });
  panel.querySelector("#resend-verify")?.addEventListener("click", async () => {
    try {
      await resendVerification();
      showToast("Verification email sent.", "success");
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Could not send.", "error");
    }
  });

  panel.querySelector("#export-data")?.addEventListener("click", async () => {
    const btn = panel.querySelector("#export-data") as HTMLButtonElement;
    btn.disabled = true;
    try {
      const blob = await downloadAccountExport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `frogswork-export-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Export downloaded. Keep it somewhere safe.", "success");
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Export failed.", "error");
    } finally {
      btn.disabled = false;
    }
  });

  panel.querySelector("#tax-export")?.addEventListener("click", async () => {
    const btn = panel.querySelector("#tax-export") as HTMLButtonElement;
    const fyEl = panel.querySelector("#tax-fy") as HTMLSelectElement | null;
    const bizEl = panel.querySelector("#tax-business") as HTMLSelectElement | null;
    const fy = String(fyEl?.value || "").trim();
    if (!fy) {
      showToast("Choose a financial year.", "error");
      return;
    }
    btn.disabled = true;
    try {
      const blob = await downloadTaxExport({
        fy,
        business: String(bizEl?.value || "").trim() || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `frogswork-tax-export-${fy}-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Tax pack downloaded.", "success");
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Tax export failed.", "error");
    } finally {
      btn.disabled = false;
    }
  });

  panel.querySelector("#wipe-data")?.addEventListener("click", () => {
    void confirmWipeData(panel, ctx);
  });
  panel.querySelector("#delete-account")?.addEventListener("click", () => {
    void confirmDeleteAccount();
  });
}

async function confirmWipeData(panel: HTMLElement, ctx: AppContext) {
  const confirmed = await openTypedConfirm({
    title: "Delete all my data",
    bodyHtml: `
      <p class="hint">Removes businesses, customers, invoices, and PDFs from FrogsWork Cloud. Your login and subscription stay.</p>
      <p class="hint"><strong>This cannot be undone and cannot be restored to FrogsWork.</strong></p>`,
    confirmPhrase: "DELETE DATA",
    confirmLabel: "Delete data",
    inputId: "wipe-confirm-input",
  });
  if (!confirmed) return;
  try {
    await deleteAccountData();
    await cache.clearAll();
    await pullBootstrap();
    showToast("All Cloud data deleted.", "success");
    await renderAccount(panel, ctx);
  } catch (ex) {
    showToast(ex instanceof Error ? ex.message : "Could not delete data.", "error");
  }
}

async function confirmDeleteAccount() {
  const confirmed = await openTypedConfirm({
    title: "Delete account",
    bodyHtml: `
      <p class="hint">This cancels your Stripe subscription immediately and permanently erases your FrogsWork Cloud account and data.</p>
      <p class="hint"><strong>This cannot be undone and cannot be restored.</strong></p>
      <div class="field" style="margin-top:0.75rem">
        <label for="delete-account-password">Password</label>
        <input id="delete-account-password" type="password" autocomplete="current-password" />
      </div>`,
    confirmPhrase: "DELETE ACCOUNT",
    confirmLabel: "Delete account",
    inputId: "delete-account-confirm-input",
    requirePasswordId: "delete-account-password",
  });
  if (!confirmed || confirmed === true) return;
  try {
    await deleteAccount(confirmed.password);
  } catch (ex) {
    // The purge may have completed server-side even if the response failed.
    // If the account still exists, surface the error; otherwise fall through to sign-out.
    const stillExists = await fetchAccount().then(
      () => true,
      () => false
    );
    if (stillExists) {
      showToast(ex instanceof Error ? ex.message : "Could not delete account.", "error");
      return;
    }
  }
  forceSignOut();
}

function forceSignOut() {
  clearSession();
  void cache.clearAll().catch(() => {});
  location.replace("/");
}

async function openTypedConfirm(opts: {
  title: string;
  bodyHtml: string;
  confirmPhrase: string;
  confirmLabel: string;
  inputId: string;
  requirePasswordId?: string;
}): Promise<false | true | { password: string }> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "sheet-overlay";
    overlay.innerHTML = `
      <div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(opts.title)}">
        <div class="sheet-handle" aria-hidden="true"></div>
        <h3 class="sheet-title">${esc(opts.title)}</h3>
        <div class="sheet-body">
          ${opts.bodyHtml}
          <div class="field" style="margin-top:0.75rem">
            <label for="${opts.inputId}">Type ${esc(opts.confirmPhrase)} to confirm</label>
            <input id="${opts.inputId}" type="text" autocomplete="off" />
          </div>
        </div>
        <div class="sheet-actions">
          <button type="button" class="btn secondary" data-action="cancel">Cancel</button>
          <button type="button" class="btn danger" data-action="confirm">${esc(opts.confirmLabel)}</button>
        </div>
      </div>`;
    const finish = (value: false | true | { password: string }) => {
      document.body.classList.remove("sheet-open");
      overlay.remove();
      resolve(value);
    };
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) finish(false);
    });
    overlay.querySelector('[data-action="cancel"]')?.addEventListener("click", () => finish(false));
    overlay.querySelector('[data-action="confirm"]')?.addEventListener("click", () => {
      const phraseEl = overlay.querySelector(`#${opts.inputId}`) as HTMLInputElement | null;
      if ((phraseEl?.value || "").trim() !== opts.confirmPhrase) {
        showToast(`Type ${opts.confirmPhrase} exactly to confirm.`, "error");
        return;
      }
      if (opts.requirePasswordId) {
        const pwEl = overlay.querySelector(`#${opts.requirePasswordId}`) as HTMLInputElement | null;
        const password = pwEl?.value || "";
        if (!password) {
          showToast("Password is required.", "error");
          return;
        }
        finish({ password });
        return;
      }
      finish(true);
    });
    document.body.classList.add("sheet-open");
    document.body.appendChild(overlay);
  });
}

async function renderEmailSending(panel: HTMLElement, ctx: AppContext) {
  const [settings, businesses] = await Promise.all([
    cache.getSettings(),
    cache.getBusinesses(),
  ]);
  const selfCopy = emailSelfCopyMode(settings);
  const defaultName = String(settings.default_business || Object.keys(businesses)[0] || "");
  const defaultBiz = (defaultName && businesses[defaultName]) || Object.values(businesses)[0] || {};
  const businessEmail = String(defaultBiz.email || "").trim();
  const accountEmail = String(ctx.account?.email || "").trim();
  const copyTarget = businessEmail || accountEmail || "your business email";
  const copyHint = businessEmail
    ? `Optionally send a copy to your business email (${esc(copyTarget)}). Change it under Business details.`
    : `Optionally send a copy to your business email. Set it under Business details (defaults to your account email${accountEmail ? `: ${esc(accountEmail)}` : ""}).`;

  panel.innerHTML = `
    <form id="email-send-form" class="panel" novalidate>
      <h2>Email sending</h2>
      <p class="hint">When you tap Send, the customer gets the PDF. ${copyHint}</p>
      <div class="field">
        <label for="email_self_copy">Copy to me</label>
        <select name="email_self_copy" id="email_self_copy">
          <option value="off" ${selfCopy === "off" ? "selected" : ""}>Don't copy me</option>
          <option value="cc" ${selfCopy === "cc" ? "selected" : ""}>CC — customer sees my email</option>
          <option value="bcc" ${selfCopy === "bcc" ? "selected" : ""}>BCC — hidden from customer</option>
        </select>
      </div>
      <p class="hint">Invoice emails include your business name, amount, due date, and payment details when set. They end with a short FrogsWork note linking to frogswork.com.</p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-email-send">Save</button>
        <button type="button" class="btn secondary" id="cancel-email-send">Back</button>
      </div>
    </form>`;

  const form = panel.querySelector("#email-send-form") as HTMLFormElement;
  const guard = attachUnsavedGuard(form);

  panel.querySelector("#cancel-email-send")?.addEventListener("click", () =>
    guard.attemptLeave(() => router.navigate("settings", "general"))
  );
  panel.querySelector("#save-email-send")?.addEventListener("click", async () => {
    try {
      const fd = new FormData(form);
      const mode = String(fd.get("email_self_copy") || "cc");
      if (!["off", "cc", "bcc"].includes(mode)) throw new Error("Invalid copy option.");
      await upsertSettings({ email_self_copy: mode });
      await flushQueue(ctx.onSyncStatus);
      guard.clear();
      showToast("Email preferences saved.", "success");
      router.navigate("settings", "general");
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Save failed.", "error");
    }
  });
}

function emailSelfCopyMode(settings: Record<string, unknown>): "off" | "cc" | "bcc" {
  const raw = String(settings.email_self_copy || "").trim().toLowerCase();
  if (raw === "off" || raw === "none") return "off";
  if (raw === "bcc") return "bcc";
  if (raw === "cc") return "cc";
  const ccSelf = !(
    settings.email_cc_self === false ||
    settings.email_cc_self === 0 ||
    settings.email_cc_self === "0"
  );
  const bccSelf =
    settings.email_bcc_self === true ||
    settings.email_bcc_self === 1 ||
    settings.email_bcc_self === "1" ||
    settings.email_bcc_self === "true";
  if (bccSelf && !ccSelf) return "bcc";
  if (!ccSelf && !bccSelf) return "off";
  return "cc";
}

async function renderPaymentTerms(panel: HTMLElement, ctx: AppContext) {
  const settings = await cache.getSettings();
  const prefs = dueRuleFromSettings(settings);
  panel.innerHTML = `
    <form id="terms-form" class="panel" novalidate>
      <h2>Default payment terms</h2>
      <p class="hint">Used when creating new invoices.</p>
      ${dueRuleFieldsHtml(prefs, { showFixed: false })}
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-terms">Save</button>
        <button type="button" class="btn secondary" id="cancel-terms">Back</button>
      </div>
    </form>`;
  wireDueRuleToggles(panel);
  const form = panel.querySelector("#terms-form") as HTMLFormElement;
  const guard = attachUnsavedGuard(form);
  panel.querySelector("#cancel-terms")?.addEventListener("click", () =>
    guard.attemptLeave(() => router.navigate("settings", "general"))
  );
  panel.querySelector("#save-terms")?.addEventListener("click", async () => {
    const err = panel.querySelector("#form-error") as HTMLElement;
    err.hidden = true;
    try {
      const fd = new FormData(form);
      const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
      await upsertSettings({ due_rule_type: due.due_rule_type, due_net_days: due.due_net_days });
      await flushQueue(ctx.onSyncStatus);
      guard.clear();
      showToast("Payment terms saved.", "success");
      router.navigate("settings", "general");
    } catch (ex) {
      err.textContent = ex instanceof Error ? ex.message : "Save failed.";
      err.hidden = false;
    }
  });
}

async function renderBusiness(panel: HTMLElement, ctx: AppContext) {
  if (router.sub === "business-add" || router.sub === "business-edit") {
    return renderBusinessForm(panel, ctx);
  }
  const businesses = await cache.getBusinesses();
  const names = Object.keys(businesses);
  if (names.length <= 1) {
    const name = names[0] || "";
    return renderBusinessForm(panel, ctx, name, name ? businesses[name] : {});
  }
  panel.innerHTML = `
    <div class="panel-header">
      <h2>Business profiles</h2>
      <button type="button" class="btn small primary" id="add-business">Add</button>
    </div>
    ${names.map((n) => businessCard(n, businesses[n])).join("")}
    <button type="button" class="btn secondary" id="back-settings">Back</button>`;
  panel.querySelector("#add-business")?.addEventListener("click", () =>
    router.navigate("settings", "business-add")
  );
  panel.querySelector("#back-settings")?.addEventListener("click", () =>
    router.navigate("settings")
  );
  panel.querySelectorAll("[data-edit-business]").forEach((btn) => {
    btn.addEventListener("click", () =>
      router.navigate("settings", "business-edit", {
        name: (btn as HTMLElement).dataset.editBusiness || "",
      })
    );
  });
}

function businessCard(name: string, record: Record<string, unknown>) {
  const display = String(record.business_name || name);
  const addr = formatAddressMultiline(record);
  return `<article class="card card-click" data-edit-business="${esc(name)}">
    <strong>${esc(display)}</strong>
    <div class="meta">${esc(addr.split("\n")[0] || "No address")}</div>
  </article>`;
}

async function renderBusinessForm(
  panel: HTMLElement,
  ctx: AppContext,
  forcedName: string | null = null,
  forcedRecord: Record<string, unknown> | null = null
) {
  const businesses = await cache.getBusinesses();
  const settings = await cache.getSettings();
  const editingName = forcedName ?? (router.params.name || "");
  const isAdd =
    router.sub === "business-add" || !editingName || !businesses[editingName];
  const record =
    forcedRecord ?? (editingName ? businesses[editingName] || {} : {});
  const accountEmail = String(ctx.account?.email || "").trim();
  const emailValue = String(record.email || "").trim() || accountEmail;
  let logoState: LogoEditorState = readLogoStateFromRecord(record);
  let guard: ReturnType<typeof attachUnsavedGuard> | null = null;

  const backTo = () => {
    if (Object.keys(businesses).length > 1 && !isAdd) router.navigate("settings", "business");
    else router.navigate("settings");
  };

  const paintForm = () => {
    panel.innerHTML = `
    <form id="business-form" class="panel" novalidate>
      <h2>${isAdd ? "Add business" : "Business details"}</h2>
      <p class="hint">Required fields are marked with *. This email is used when you CC/BCC yourself on invoice emails.</p>
      <div class="field"><label>Business name *</label>
        <input name="business_name" value="${esc(record.business_name || editingName)}" required autocomplete="organization"></div>
      <div class="field"><label>Email *</label>
        <input name="email" type="email" value="${esc(emailValue)}" required autocomplete="email">
        <p class="hint">Defaults to your account email. Change it if invoices should copy a different address.</p></div>
      <div class="field"><label>Phone (optional)</label>
        <input name="phone" value="${esc(record.phone || "")}" type="tel" autocomplete="tel"></div>
      ${businessAddressFieldsHtml(record)}
      ${gstFieldsHtml(record)}
      ${bankFieldsHtml(record)}
      <h3>Invoice logo (optional)</h3>
      ${logoEditorHtml(logoState)}
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-business">Save</button>
        <button type="button" class="btn secondary" id="back-settings">Back</button>
      </div>
    </form>`;

    const form = panel.querySelector("#business-form") as HTMLFormElement;
    guard = attachUnsavedGuard(form);

    const gstSelect = form.querySelector("#gst_registered") as HTMLSelectElement | null;
    const syncAbnRequired = () => {
      const yes = parseGstRegisteredForm(gstSelect?.value);
      form.querySelectorAll("[data-abn-req]").forEach((el) =>
        (el as HTMLElement).toggleAttribute("hidden", !yes)
      );
      form.querySelectorAll("[data-abn-opt]").forEach((el) =>
        (el as HTMLElement).toggleAttribute("hidden", yes)
      );
    };
    gstSelect?.addEventListener("change", syncAbnRequired);
    syncAbnRequired();

    const onLogoChange = (next: LogoEditorState, reason: "source" | "placement" | "enabled") => {
      logoState = next;
      if (reason === "source") {
        refreshLogoEditorSection(panel, logoState, onLogoChange);
      }
    };
    wireLogoEditor(panel, logoState, onLogoChange);

    panel.querySelector("#back-settings")?.addEventListener("click", () => {
      guard?.attemptLeave(backTo);
    });

    panel.querySelector("#save-business")?.addEventListener("click", async () => {
      const err = panel.querySelector("#form-error") as HTMLElement;
      const saveBtn = panel.querySelector("#save-business") as HTMLButtonElement | null;
      err.hidden = true;
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving…";
      }
      try {
        const fd = new FormData(form);
        const businessName = String(fd.get("business_name") || "").trim();
        if (!businessName) throw new Error("Business name is required.");
        const email = String(fd.get("email") || "").trim();
        if (!email || !email.includes("@")) throw new Error("A valid email is required.");
        const addr = normalizeAuAddress(readAddressFromForm(fd));
        if (!addr.address_line1) throw new Error("Street or PO Box is required.");
        if (!addr.suburb) throw new Error("Suburb is required.");
        if (!addr.state) throw new Error("State is required.");
        if (!addr.postcode) throw new Error("Postcode is required.");
        const accountName = String(fd.get("account_name") || "").trim();
        if (!accountName) throw new Error("Account name is required.");
        const bsbRaw = String(fd.get("bsb") || "").trim();
        const accRaw = String(fd.get("acc") || "").trim();
        if (!bsbRaw) throw new Error("BSB is required.");
        if (!accRaw) throw new Error("Account number is required.");
        if (logoState.enabled && logoState.sourceB64 && !logoState.bakedB64) {
          logoState.bakedB64 = await bakeLogoToHeaderSlot(logoState.sourceB64, logoState.placement);
        }
        const profile: Record<string, unknown> = {
          business_name: businessName,
          email,
          phone: String(fd.get("phone") || "").trim(),
          ...addr,
          business_abn: fd.get("business_abn")
            ? normalizeAbn(String(fd.get("business_abn")))
            : "",
          gst_registered: parseGstRegisteredForm(fd.get("gst_registered")),
          bsb: normalizeBsb(bsbRaw),
          acc: normalizeAccountNumber(accRaw),
          account_name: accountName,
          invoice_counter: record.invoice_counter || 1,
          logo_b64: logoState.bakedB64 || "",
          logo_source_b64: logoState.sourceB64 || "",
          logo_placement: logoState.placement,
          logo_enabled: logoState.enabled && Boolean(logoState.bakedB64),
        };
        const gstErr = validateBusinessGstSettings(profile);
        if (gstErr) throw new Error(gstErr);
        const key = isAdd ? businessName : editingName || businessName;
        if (isAdd && businesses[businessName]) {
          throw new Error("A business with this name already exists.");
        }
        await upsertBusiness(key, profile);
        if (!settings.default_business) await upsertSettings({ default_business: key });
        guard?.clear();
        showToast("Business saved.", "success");
        router.navigate("settings");
        // Sync in background so large logos don't freeze the Save click.
        void flushQueue(ctx.onSyncStatus).then((flush) => {
          if (!flush.ok) {
            showToast(flush.error || "Saved locally but sync failed. Will retry when online.", "error");
          }
        });
      } catch (ex) {
        err.textContent = ex instanceof Error ? ex.message : "Save failed.";
        err.hidden = false;
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Save";
        }
      }
    });
  };

  paintForm();
}
