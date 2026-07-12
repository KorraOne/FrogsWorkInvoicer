import { cache } from "../idb.js";
import { upsertBusiness, upsertSettings, flushQueue } from "../sync.js";
import {
  normalizeAuAddress,
  normalizeAbn,
  normalizeBsb,
  normalizeAccountNumber,
  formatAddressMultiline,
} from "../domain/address.js";
import { parseGstRegisteredForm, validateBusinessGstSettings } from "../domain/gst.js";
import { dueRuleFromFormData } from "../domain/due_dates.js";
import {
  addressFields,
  gstFields,
  bankFields,
  dueRuleFields,
  wireDueRuleToggles,
  readAddressFromForm,
} from "../components/forms.js";
import { router } from "../router.js";

export async function renderBusiness(panel, ctx) {
  if (router.sub === "edit" || router.sub === "add") {
    return renderBusinessForm(panel, ctx);
  }
  const businesses = await cache.getBusinesses();
  const names = Object.keys(businesses);
  if (names.length <= 1 && router.sub === "business") {
    const name = names[0] || "";
    return renderBusinessForm(panel, ctx, name, name ? businesses[name] : {});
  }
  panel.innerHTML = `
    <div class="panel-header"><h2>Business profiles</h2>
      <button type="button" class="btn small primary" id="add-business">Add business</button></div>
    ${names.length ? names.map((n) => businessCard(n, businesses[n])).join("") : '<p class="hint">No business profile yet.</p>'}`;
  panel.querySelector("#add-business")?.addEventListener("click", () => router.navigate("settings", "business-add"));
  panel.querySelectorAll("[data-edit-business]").forEach((btn) => {
    btn.addEventListener("click", () => router.navigate("settings", "business-edit", { name: btn.dataset.editBusiness }));
  });
}

function businessCard(name, record) {
  const display = record.business_name || name;
  const addr = formatAddressMultiline(record);
  return `<article class="card card-click" data-edit-business="${esc(name)}">
    <strong>${esc(display)}</strong>
    <div class="meta">${esc(addr.split("\n")[0] || "No address")}</div>
  </article>`;
}

async function renderBusinessForm(panel, ctx, forcedName = null, forcedRecord = null) {
  const editingName = forcedName ?? (router.params.name || router.params.id || "");
  const isAdd = router.sub === "business-add" || router.sub === "add" || (!editingName && router.sub !== "business-edit");
  const businesses = await cache.getBusinesses();
  const settings = await cache.getSettings();
  const record = forcedRecord ?? (editingName ? businesses[editingName] || {} : {});
  const duePrefs = {
    due_rule_type: settings.due_rule_type || "net_days",
    due_net_days: settings.due_net_days || 14,
  };

  panel.innerHTML = `
    <form id="business-form" class="panel">
      <h2>${isAdd ? "Add business" : "Business details"}</h2>
      <div class="field"><label>Business name</label>
        <input name="business_name" value="${esc(record.business_name || editingName)}" required ${!isAdd && editingName ? "" : ""}></div>
      ${addressFields("", record)}
      ${gstFields(record)}
      ${bankFields(record)}
      ${!isAdd && router.sub !== "business-add" ? "" : dueRuleFields(duePrefs, { showFixed: false })}
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="submit" class="btn primary">Save</button>
        <button type="button" class="btn secondary" id="cancel-business">Cancel</button>
      </div>
    </form>`;
  wireDueRuleToggles(panel);
  document.getElementById("cancel-business").addEventListener("click", () => router.navigate("settings"));
  document.getElementById("business-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("form-error");
    err.hidden = true;
    try {
      const fd = new FormData(e.target);
      const businessName = (fd.get("business_name") || "").trim();
      if (!businessName) throw new Error("Business name is required.");
      const addr = normalizeAuAddress(readAddressFromForm(fd));
      const profile = {
        business_name: businessName,
        ...addr,
        business_abn: normalizeAbn(fd.get("business_abn") || ""),
        gst_registered: parseGstRegisteredForm(fd.get("gst_registered")),
        bsb: normalizeBsb(fd.get("bsb") || ""),
        acc: normalizeAccountNumber(fd.get("acc") || ""),
        account_name: (fd.get("account_name") || "").trim(),
        invoice_counter: record.invoice_counter || 1,
      };
      const gstErr = validateBusinessGstSettings(profile);
      if (gstErr) throw new Error(gstErr);
      const key = isAdd ? businessName : editingName || businessName;
      if (isAdd && businesses[businessName]) throw new Error("A business with this name already exists.");
      await upsertBusiness(key, profile);
      if (!settings.default_business) await upsertSettings({ default_business: key });
      if (fd.get("due_rule_type")) {
        const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
        await upsertSettings({ due_rule_type: due.due_rule_type, due_net_days: due.due_net_days });
      }
      await flushQueue(ctx.onSyncStatus);
      router.navigate("settings");
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

export { renderBusinessForm };
