import { VALID_DUE_RULE_TYPES } from "../domain/dueDates";
import { AU_STATES } from "../domain/address";
import { esc } from "../lib/escape";

export function gstFieldsHtml(values: Record<string, unknown> = {}): string {
  const yes = Boolean(values.gst_registered);
  return `
    <div class="field">
      <label for="gst_registered">Registered for GST?</label>
      <p class="hint">Only GST-registered businesses can issue a Tax Invoice. Most sole traders are not registered.
        <a href="https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/registering-for-gst" target="_blank" rel="noopener noreferrer">ATO: registering for GST</a>
      </p>
      <select name="gst_registered" id="gst_registered">
        <option value="yes" ${yes ? "selected" : ""}>Yes</option>
        <option value="no" ${!yes ? "selected" : ""}>No</option>
      </select>
    </div>
    <div class="field"><label>Business ABN</label>
      <input name="business_abn" value="${esc(values.business_abn || values.abn || "")}" inputmode="numeric" placeholder="11 digits"></div>`;
}

export function bankFieldsHtml(values: Record<string, unknown> = {}): string {
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

export function dueRuleFieldsHtml(
  values: Record<string, unknown> = {},
  { showFixed = true }: { showFixed?: boolean } = {}
): string {
  const type = String(values.due_rule_type || "net_days");
  const types = showFixed
    ? [...VALID_DUE_RULE_TYPES]
    : VALID_DUE_RULE_TYPES.filter((t) => t !== "fixed_date");
  const labels: Record<string, string> = {
    net_days: "Net days after invoice date",
    end_next_week: "End of next week",
    end_next_month: "End of next month",
    fixed_date: "Specific date",
  };
  return `
    <div class="field">
      <label for="due_rule_type">Payment due</label>
      <select name="due_rule_type" id="due_rule_type">
        ${types
          .map(
            (t) =>
              `<option value="${t}" ${type === t ? "selected" : ""}>${labels[t]}</option>`
          )
          .join("")}
      </select>
    </div>
    <div class="field due-net-days" ${type !== "net_days" ? "hidden" : ""}>
      <label>Days after invoice date</label>
      <input type="number" name="due_net_days" min="1" max="365" value="${values.due_net_days || 14}"></div>
    <div class="field due-fixed-date" ${type !== "fixed_date" ? "hidden" : ""}>
      <label>Due date</label>
      <input type="date" name="due_fixed_date" value="${esc(values.due_fixed_date || "")}"></div>`;
}

export function wireDueRuleToggles(root: ParentNode) {
  const select = root.querySelector('select[name="due_rule_type"]') as HTMLSelectElement | null;
  const sync = () => {
    const t = select?.value || "net_days";
    root.querySelector(".due-net-days")?.toggleAttribute("hidden", t !== "net_days");
    root.querySelector(".due-fixed-date")?.toggleAttribute("hidden", t !== "fixed_date");
  };
  select?.addEventListener("change", sync);
  sync();
}

/** Visual zone card for create/settings forms. */
export function formSectionHtml(title: string, bodyHtml: string): string {
  return `<section class="form-section">
    <h3 class="form-section-title">${esc(title)}</h3>
    <div class="form-section-body">${bodyHtml}</div>
  </section>`;
}

/** Collapsible block: summary row + optional Adjust / body. */
export function disclosureBlockHtml(opts: {
  id: string;
  summaryHtml: string;
  bodyHtml: string;
  defaultOpen?: boolean;
  toggleLabel?: string;
  toggleLabelOpen?: string;
}): string {
  const open = Boolean(opts.defaultOpen);
  const closedLabel = opts.toggleLabel || "Adjust";
  const openLabel = opts.toggleLabelOpen || "Done";
  return `
    <div class="disclosure" id="${esc(opts.id)}" data-open="${open ? "1" : "0"}">
      <div class="disclosure-bar">
        <div class="disclosure-summary">${opts.summaryHtml}</div>
        <button type="button" class="btn small ghost disclosure-toggle" data-disclosure="${esc(opts.id)}"
          data-closed-label="${esc(closedLabel)}" data-open-label="${esc(openLabel)}"
          aria-expanded="${open ? "true" : "false"}">${open ? openLabel : closedLabel}</button>
      </div>
      <div class="disclosure-body" ${open ? "" : "hidden"}>${opts.bodyHtml}</div>
    </div>`;
}

export function wireDisclosure(
  root: ParentNode,
  id: string,
  opts?: { closedLabel?: string; openLabel?: string; onToggle?: (open: boolean) => void }
) {
  const block = root.querySelector(`#${CSS.escape(id)}`) as HTMLElement | null;
  if (!block) return;
  const body = block.querySelector(".disclosure-body") as HTMLElement | null;
  const btn = block.querySelector(".disclosure-toggle") as HTMLButtonElement | null;
  const closedLabel = opts?.closedLabel || btn?.dataset.closedLabel || "Adjust";
  const openLabel = opts?.openLabel || btn?.dataset.openLabel || "Done";
  btn?.addEventListener("click", () => {
    const open = block.dataset.open !== "1";
    block.dataset.open = open ? "1" : "0";
    body?.toggleAttribute("hidden", !open);
    if (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? openLabel : closedLabel;
    }
    opts?.onToggle?.(open);
  });
}

export function businessAddressFieldsHtml(record: Record<string, unknown> = {}): string {
  const opts = AU_STATES.map(
    (s) => `<option value="${s}" ${record.state === s ? "selected" : ""}>${s}</option>`
  ).join("");
  return `
    <div class="field"><label>Street or PO Box</label>
      <input name="line1" value="${esc(record.address_line1)}" autocomplete="address-line1"></div>
    <div class="field"><label>Unit, level, suite (optional)</label>
      <input name="line2" value="${esc(record.address_line2)}" autocomplete="address-line2"></div>
    <div class="field-row">
      <div class="field"><label>Suburb</label><input name="suburb" value="${esc(record.suburb)}"></div>
      <div class="field field-narrow"><label>State</label>
        <select name="state"><option value="">—</option>${opts}</select></div>
      <div class="field field-narrow"><label>Postcode</label>
        <input name="postcode" value="${esc(record.postcode)}" inputmode="numeric" maxlength="4"></div>
    </div>`;
}
