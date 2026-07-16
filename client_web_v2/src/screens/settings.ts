import { resendVerification } from "../api/mobile";
import {
  bankFieldsHtml,
  businessAddressFieldsHtml,
  dueRuleFieldsHtml,
  gstFieldsHtml,
  wireDueRuleToggles,
} from "../components/forms";
import {
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

const SUPPORT_URL = "https://korraone.com/support";

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

  panel.innerHTML = `
    <h2 class="section-title">Settings</h2>
    <a class="nav-card" href="#settings/business">
      <span class="nav-card-title">Business details</span>
      <span class="nav-card-hint">Shown on your invoices</span>
    </a>
    <a class="nav-card" href="#settings/general">
      <span class="nav-card-title">General</span>
      <span class="nav-card-hint">Payment terms and email sending</span>
    </a>
    <a class="nav-card" href="#settings/account">
      <span class="nav-card-title">Account</span>
      <span class="nav-card-hint">Subscription, sync, and sign out</span>
    </a>
    <a class="nav-card" href="${SUPPORT_URL}" target="_blank" rel="noopener">
      <span class="nav-card-title">Help &amp; support</span>
      <span class="nav-card-hint">Guides and troubleshooting</span>
    </a>`;
}

function renderGeneralHub(panel: HTMLElement) {
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
    <button type="button" class="btn secondary" id="back-settings">Back</button>`;
  panel.querySelector("#back-settings")?.addEventListener("click", () =>
    router.navigate("settings")
  );
}

async function renderAccount(panel: HTMLElement, ctx: AppContext) {
  const acc = ctx.account;
  const lastSync = localStorage.getItem("frogswork_last_sync");
  panel.innerHTML = `
    <section class="panel">
      <h2>Account</h2>
      <div class="preview-row"><span class="preview-label">Email</span><span>${esc(acc?.email || "")}</span></div>
      <div class="preview-row"><span class="preview-label">Subscription</span><span>${acc?.active ? "Active" : "Inactive"}</span></div>
      ${
        acc?.portal_url
          ? `<a class="btn secondary" href="${esc(acc.portal_url)}" target="_blank" rel="noopener">Manage subscription</a>`
          : ""
      }
      ${
        acc && !acc.email_verified
          ? `<button type="button" class="btn small secondary" id="resend-verify">Resend verification</button>`
          : ""
      }
      <div class="nav-card card-static" style="margin-top:1rem">
        <span class="nav-card-title">Sync</span>
        <span class="nav-card-hint">${lastSync ? `Last sync: ${new Date(lastSync).toLocaleString()}` : "Not synced yet"}</span>
        <button type="button" class="btn small secondary" id="sync-now">Sync now</button>
      </div>
      <div class="btn-row" style="margin-top:1rem">
        <button type="button" class="btn danger" id="sign-out">Sign out</button>
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
}

async function renderEmailSending(panel: HTMLElement, ctx: AppContext) {
  const settings = await cache.getSettings();
  const selfCopy = emailSelfCopyMode(settings);
  const accountEmail = ctx.account?.email || "your account email";

  panel.innerHTML = `
    <form id="email-send-form" class="panel" novalidate>
      <h2>Email sending</h2>
      <p class="hint">When you tap Send, the customer gets the PDF. Optionally send a copy to ${esc(accountEmail)}.</p>
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
  const duePrefs = dueRuleFromSettings(settings);
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
      <div class="field"><label>Business name</label>
        <input name="business_name" value="${esc(record.business_name || editingName)}" required></div>
      <div class="field"><label>Email</label><input name="email" type="email" value="${esc(record.email)}"></div>
      <div class="field"><label>Phone</label><input name="phone" value="${esc(record.phone)}"></div>
      ${businessAddressFieldsHtml(record)}
      ${gstFieldsHtml(record)}
      ${bankFieldsHtml(record)}
      <h3>Invoice logo</h3>
      ${logoEditorHtml(logoState)}
      ${isAdd ? dueRuleFieldsHtml(duePrefs, { showFixed: false }) : ""}
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-business">Save</button>
        <button type="button" class="btn secondary" id="back-settings">Back</button>
      </div>
    </form>`;

    if (isAdd) wireDueRuleToggles(panel);

    const form = panel.querySelector("#business-form") as HTMLFormElement;
    guard = attachUnsavedGuard(form);

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
      err.hidden = true;
      try {
        const fd = new FormData(panel.querySelector("#business-form") as HTMLFormElement);
        const businessName = String(fd.get("business_name") || "").trim();
        if (!businessName) throw new Error("Business name is required.");
        const addr = normalizeAuAddress(readAddressFromForm(fd));
        const profile: Record<string, unknown> = {
          business_name: businessName,
          email: String(fd.get("email") || "").trim(),
          phone: String(fd.get("phone") || "").trim(),
          ...addr,
          business_abn: fd.get("business_abn")
            ? normalizeAbn(String(fd.get("business_abn")))
            : "",
          gst_registered: parseGstRegisteredForm(fd.get("gst_registered")),
          bsb: fd.get("bsb") ? normalizeBsb(String(fd.get("bsb"))) : "",
          acc: fd.get("acc") ? normalizeAccountNumber(String(fd.get("acc"))) : "",
          account_name: String(fd.get("account_name") || "").trim(),
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
        if (fd.get("due_rule_type")) {
          const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
          await upsertSettings({
            due_rule_type: due.due_rule_type,
            due_net_days: due.due_net_days,
          });
        }
        const flush = await flushQueue(ctx.onSyncStatus);
        if (!flush.ok) {
          throw new Error(flush.error || "Saved locally but sync failed. Try again when online.");
        }
        guard?.clear();
        showToast("Business saved.", "success");
        router.navigate("settings");
      } catch (ex) {
        err.textContent = ex instanceof Error ? ex.message : "Save failed.";
        err.hidden = false;
      }
    });
  };

  paintForm();
}
