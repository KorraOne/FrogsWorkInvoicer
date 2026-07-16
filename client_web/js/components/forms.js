import { AU_STATES, normalizeAuAddress } from "../domain/address.js";
import { VALID_DUE_RULE_TYPES } from "../domain/due_dates.js";

export function addressFields(prefix = "", values = {}) {
  const p = prefix ? `${prefix}_` : "";
  const v = (k) => values[k] || values[`${prefix ? prefix + "_" : ""}${k}`] || "";
  return `
    <div class="field"><label>Street or PO Box</label>
      <input name="${p}address_line1" value="${esc(v("address_line1"))}" autocomplete="address-line1"></div>
    <div class="field"><label>Unit, level, suite (optional)</label>
      <input name="${p}address_line2" value="${esc(v("address_line2"))}" autocomplete="address-line2"></div>
    <div class="field-row">
      <div class="field"><label>Suburb</label>
        <input name="${p}suburb" value="${esc(v("suburb"))}"></div>
      <div class="field field-narrow"><label>State</label>
        <select name="${p}state">
          <option value="">—</option>
          ${AU_STATES.map((s) => `<option value="${s}" ${v("state") === s ? "selected" : ""}>${s}</option>`).join("")}
        </select></div>
      <div class="field field-narrow"><label>Postcode</label>
        <input name="${p}postcode" value="${esc(v("postcode"))}" inputmode="numeric" maxlength="4"></div>
    </div>`;
}

export function gstFields(values = {}) {
  const yes = values.gst_registered ? "checked" : "";
  const no = !values.gst_registered ? "checked" : "";
  return `
    <fieldset class="field">
      <legend>Are you registered for GST?</legend>
      <label class="radio"><input type="radio" name="gst_registered" value="yes" ${yes}> Yes</label>
      <label class="radio"><input type="radio" name="gst_registered" value="no" ${no}> No</label>
    </fieldset>
    <div class="field"><label>Business ABN</label>
      <input name="business_abn" value="${esc(values.business_abn || values.abn || "")}" inputmode="numeric" placeholder="11 digits"></div>`;
}

export function bankFields(values = {}) {
  return `
    <div class="field-row">
      <div class="field"><label>BSB</label>
        <input name="bsb" value="${esc(values.bsb || "")}" inputmode="numeric" placeholder="000-000"></div>
      <div class="field"><label>Account number</label>
        <input name="acc" value="${esc(values.acc || "")}" inputmode="numeric"></div>
    </div>
    <div class="field"><label>Account name</label>
      <input name="account_name" value="${esc(values.account_name || "")}"></div>`;
}

export function dueRuleFields(values = {}, { showFixed = true } = {}) {
  const type = values.due_rule_type || "net_days";
  const types = showFixed ? VALID_DUE_RULE_TYPES : VALID_DUE_RULE_TYPES.filter((t) => t !== "fixed_date");
  return `
    <fieldset class="field">
      <legend>Payment due</legend>
      ${types
        .map((t) => {
          const labels = {
            net_days: "Net days after invoice date",
            end_next_week: "End of next week",
            end_next_month: "End of next month",
            fixed_date: "Specific date",
          };
          return `<label class="radio"><input type="radio" name="due_rule_type" value="${t}" ${type === t ? "checked" : ""}> ${labels[t]}</label>`;
        })
        .join("")}
    </fieldset>
    <div class="field due-net-days" ${type !== "net_days" ? "hidden" : ""}>
      <label>Days after invoice date</label>
      <input type="number" name="due_net_days" min="1" max="365" value="${values.due_net_days || 14}"></div>
    <div class="field due-fixed-date" ${type !== "fixed_date" ? "hidden" : ""}>
      <label>Due date</label>
      <input type="date" name="due_fixed_date" value="${values.due_fixed_date || ""}"></div>`;
}

export function wireDueRuleToggles(root) {
  root.querySelectorAll('input[name="due_rule_type"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const t = root.querySelector('input[name="due_rule_type"]:checked')?.value;
      root.querySelector(".due-net-days")?.toggleAttribute("hidden", t !== "net_days");
      root.querySelector(".due-fixed-date")?.toggleAttribute("hidden", t !== "fixed_date");
    });
  });
}

export function readAddressFromForm(fd, prefix = "") {
  const p = prefix ? `${prefix}_` : "";
  return {
    address_line1: fd.get(`${p}address_line1`) || "",
    address_line2: fd.get(`${p}address_line2`) || "",
    suburb: fd.get(`${p}suburb`) || "",
    state: fd.get(`${p}state`) || "",
    postcode: fd.get(`${p}postcode`) || "",
  };
}

export function readAndNormalizeAddress(fd, prefix = "") {
  const raw = readAddressFromForm(fd, prefix);
  return normalizeAuAddress({
    line1: raw.address_line1,
    line2: raw.address_line2,
    suburb: raw.suburb,
    state: raw.state,
    postcode: raw.postcode,
  });
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}
