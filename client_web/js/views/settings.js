import { api } from "../api.js";
import { cache } from "../idb.js";
import { pullBootstrap, flushQueue, upsertSettings } from "../sync.js";
import { dueRuleFields, wireDueRuleToggles } from "../components/forms.js";
import { dueRuleFromFormData } from "../domain/due_dates.js";
import { router } from "../router.js";
import { renderBusiness, renderBusinessForm } from "./business.js";

export async function renderSettings(panel, ctx) {
  if (router.sub === "business" || router.sub === "business-edit" || router.sub === "business-add") {
    if (router.sub === "business") return renderBusiness(panel, ctx);
    const name = router.params.name || router.params.id || "";
    const businesses = await cache.getBusinesses();
    if (router.sub === "business-add") return renderBusinessForm(panel, ctx);
    return renderBusinessForm(panel, ctx, name, businesses[name] || {});
  }
  if (router.sub === "payment-terms") return renderPaymentTerms(panel, ctx);
  if (router.sub === "account") return renderAccount(panel, ctx);

  const settings = await cache.getSettings();
  const lastSync = localStorage.getItem("frogswork_last_sync");
  panel.innerHTML = `
    <h2 class="section-title">Settings</h2>
    <a class="nav-card" href="#settings/account"><span class="nav-card-title">Your account</span><span class="nav-card-hint">Sign in and subscription</span></a>
    <a class="nav-card" href="#settings/business"><span class="nav-card-title">Business details</span><span class="nav-card-hint">Shown on your invoices</span></a>
    <a class="nav-card" href="#settings/payment-terms"><span class="nav-card-title">Payment terms</span><span class="nav-card-hint">Default due date for new invoices</span></a>
    <div class="nav-card card-static">
      <span class="nav-card-title">Sync</span>
      <span class="nav-card-hint">${lastSync ? `Last sync: ${new Date(lastSync).toLocaleString()}` : "Not synced yet"}</span>
      <button type="button" class="btn small secondary" id="sync-now">Sync now</button>
    </div>
    <a class="nav-card" href="https://frogswork.com/support.html" target="_blank" rel="noopener"><span class="nav-card-title">Help &amp; support</span><span class="nav-card-hint">Install help and troubleshooting</span></a>
    <div class="btn-row"><button type="button" class="btn danger" id="sign-out">Sign out</button></div>`;
  panel.querySelector("#sync-now")?.addEventListener("click", async () => {
    try {
      await pullBootstrap();
      await flushQueue(ctx.onSyncStatus);
      await renderSettings(panel, ctx);
    } catch (ex) {
      alert(ex.message);
    }
  });
  panel.querySelector("#sign-out")?.addEventListener("click", () => {
    api.clearSession();
    location.reload();
  });
}

async function renderPaymentTerms(panel, ctx) {
  const settings = await cache.getSettings();
  panel.innerHTML = `
    <form id="terms-form" class="panel">
      <h2>Default payment terms</h2>
      <p class="hint">Used when creating new invoices.</p>
      ${dueRuleFields(settings, { showFixed: false })}
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="submit" class="btn primary">Save</button>
        <button type="button" class="btn secondary" id="cancel-terms">Back</button>
      </div>
    </form>`;
  wireDueRuleToggles(panel);
  document.getElementById("cancel-terms").addEventListener("click", () => router.navigate("settings"));
  document.getElementById("terms-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("form-error");
    err.hidden = true;
    try {
      const fd = new FormData(e.target);
      const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
      await upsertSettings({ due_rule_type: due.due_rule_type, due_net_days: due.due_net_days });
      await flushQueue(ctx.onSyncStatus);
      router.navigate("settings");
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

async function renderAccount(panel, ctx) {
  let ent = ctx.entitlements;
  if (!ent) {
    try {
      ent = await api.entitlements();
      ctx.entitlements = ent;
    } catch {
      ent = null;
    }
  }
  const portalUrl = ent?.portal_url || "";
  const needsVerify = ent && ent.email_verified === false;
  panel.innerHTML = `
    <section class="panel">
      <h2>Your account</h2>
      <div class="preview-row"><span class="preview-label">Subscription</span><span>${ent?.active ? "Active" : "Inactive"}</span></div>
      ${needsVerify ? `<p class="hint warn">Please verify your email. <button type="button" class="btn small secondary" id="resend-verify">Resend verification</button></p>` : ""}
      ${portalUrl ? `<a class="btn secondary" href="${portalUrl}" target="_blank" rel="noopener">Manage subscription</a>` : ""}
      <a class="btn secondary" href="https://frogswork.com/account/subscribe.html">Subscribe</a>
      <button type="button" class="btn secondary" id="back-settings">Back</button>
    </section>`;
  document.getElementById("back-settings").addEventListener("click", () => router.navigate("settings"));
  document.getElementById("resend-verify")?.addEventListener("click", async () => {
    try {
      await api.resendVerification();
      alert("Verification email sent.");
    } catch (ex) {
      alert(ex.message);
    }
  });
}
