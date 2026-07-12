import { cache } from "../idb.js";
import { createInvoiceOffline, bumpInvoiceCounter, flushQueue } from "../sync.js";
import { parseLineItems, isGstRegistered } from "../domain/gst.js";
import {
  formatMoney,
  moneyStr,
  parseInvoiceNumberInput,
  suggestedInvoiceNumber,
  todayIso,
  formatInvoiceNumber,
  formatInvoiceDate,
  formatAbn,
} from "../domain/invoice_format.js";
import { dueRuleFromFormData, invoiceDueSummary } from "../domain/due_dates.js";
import { formatAddressMultiline } from "../domain/address.js";
import { dueRuleFields, wireDueRuleToggles } from "../components/forms.js";
import { router } from "../router.js";

let draft = null;

export async function renderInvoiceCreate(panel, ctx) {
  if (router.sub === "preview" && draft) {
    return renderPreview(panel, ctx);
  }
  const [businesses, customers, invoices, settings] = await Promise.all([
    cache.getBusinesses(),
    cache.getCustomers(),
    cache.getInvoices(),
    cache.getSettings(),
  ]);
  const bizNames = Object.keys(businesses);
  const defaultBiz = settings.default_business && businesses[settings.default_business]
    ? settings.default_business
    : bizNames[0] || "";
  const biz = businesses[defaultBiz] || {};
  const gstReg = isGstRegistered(biz);
  const suggested = suggestedInvoiceNumber(defaultBiz, biz, invoices);
  const duePrefs = dueRuleFromFormData({}, settings);
  const custNames = Object.keys(customers).sort();

  panel.innerHTML = `
    <form id="create-invoice-form" class="panel">
      <h2>Create sales invoice</h2>
      ${bizNames.length > 1 ? `<div class="field"><label>Invoice from</label><select name="business">${bizNames.map((n) => `<option value="${esc(n)}" ${n === defaultBiz ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>` : `<input type="hidden" name="business" value="${esc(defaultBiz)}">`}
      <div class="field-row">
        <div class="field"><label>Invoice number</label><input name="invoice_number" value="${suggested}" required inputmode="numeric"></div>
        <div class="field"><label>Date</label><input type="date" name="invoice_date" value="${todayIso()}" readonly></div>
      </div>
      <div class="field"><label>Customer</label>
        <select name="customer" required>
          <option value="">Select customer</option>
          ${custNames.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")}
        </select>
        <button type="button" class="btn small ghost" id="add-customer-inline">Add customer</button>
      </div>
      <div id="line-items">
        <h3>Line items</h3>
        ${lineItemRow({ gstReg })}
      </div>
      <button type="button" class="btn small secondary" id="add-line">+ Add line</button>
      ${dueRuleFields(duePrefs, { showFixed: true })}
      <div class="field"><label>Notes (optional)</label><textarea name="comment" rows="2"></textarea></div>
      <div class="preview-section totals-panel" id="live-totals"></div>
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="submit" class="btn primary">Preview invoice</button>
        <button type="button" class="btn secondary" id="cancel-create">Cancel</button>
      </div>
    </form>`;

  wireDueRuleToggles(panel);
  const form = panel.querySelector("#create-invoice-form");
  const updateTotals = () => {
    try {
      const fd = new FormData(form);
      const rows = readLineItems(form, gstReg);
      const { gstAmount, totalIncGst, taxableExGst, gstFreeExGst } = parseLineItems(rows, gstReg);
      panel.querySelector("#live-totals").innerHTML = totalsHtml(gstReg, taxableExGst, gstFreeExGst, gstAmount, totalIncGst);
    } catch {
      panel.querySelector("#live-totals").innerHTML = "";
    }
  };
  form.addEventListener("input", updateTotals);
  updateTotals();

  panel.querySelector("#add-line")?.addEventListener("click", () => {
    const wrap = document.createElement("div");
    wrap.className = "line-item";
    wrap.innerHTML = lineItemRow({ gstReg, removable: true });
    panel.querySelector("#line-items").appendChild(wrap);
    wrap.querySelector(".remove-line")?.addEventListener("click", () => {
      wrap.remove();
      updateTotals();
    });
    updateTotals();
  });

  panel.querySelector("#add-customer-inline")?.addEventListener("click", () => router.navigate("customers", "add"));
  panel.querySelector("#cancel-create")?.addEventListener("click", () => router.navigate("invoices"));

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const err = panel.querySelector("#form-error");
    err.hidden = true;
    try {
      const fd = new FormData(form);
      const businessName = fd.get("business") || defaultBiz;
      const business = businesses[businessName] || biz;
      const gstRegistered = isGstRegistered(business);
      const rows = readLineItems(form, gstRegistered);
      const parsed = parseLineItems(rows, gstRegistered);
      const customerName = (fd.get("customer") || "").trim();
      if (!customerName) throw new Error("Select a customer.");
      const invoiceNumber = parseInvoiceNumberInput(fd.get("invoice_number"));
      const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
      const dueSummary = invoiceDueSummary(fd.get("invoice_date") || todayIso(), due.due_rule_type, due.due_net_days, due.due_fixed_date);
      const description = parsed.items.map((i) => i.description).join("; ");
      draft = {
        invoice_number: invoiceNumber,
        invoice_date: fd.get("invoice_date") || todayIso(),
        customer_name: customerName,
        business_name: businessName,
        line_items: parsed.items,
        description,
        amount_ex_gst: moneyStr(parsed.subtotal),
        gst_amount: moneyStr(parsed.gstAmount),
        total_inc_gst: moneyStr(parsed.totalIncGst),
        taxable_ex_gst: moneyStr(parsed.taxableExGst),
        gst_free_ex_gst: moneyStr(parsed.gstFreeExGst),
        gst_registered: gstRegistered,
        due_rule_type: due.due_rule_type,
        due_net_days: due.due_net_days,
        due_fixed_date: due.due_fixed_date,
        due_date: dueSummary.due_date_iso,
        comment: (fd.get("comment") || "").trim(),
        status: "not_sent",
        pdf_status: "pending",
      };
      router.navigate("invoices", "preview");
      renderPreview(panel, ctx);
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

function lineItemRow({ gstReg, removable = false }) {
  return `<div class="line-item field-row">
    <div class="field flex-2"><label>Description</label><input name="item_description" required></div>
    <div class="field field-narrow"><label>Qty</label><input name="item_quantity" value="1" inputmode="decimal"></div>
    <div class="field"><label>Amount ex GST</label><input name="item_amount" inputmode="decimal" required></div>
    ${gstReg ? `<label class="checkbox"><input type="checkbox" name="item_gst_free"> GST-free</label>` : ""}
    ${removable ? `<button type="button" class="btn small danger remove-line">×</button>` : ""}
  </div>`;
}

function readLineItems(form, gstReg) {
  const descriptions = [...form.querySelectorAll('[name="item_description"]')].map((el) => el.value);
  const amounts = [...form.querySelectorAll('[name="item_amount"]')].map((el) => el.value);
  const quantities = [...form.querySelectorAll('[name="item_quantity"]')].map((el) => el.value);
  const gstFlags = [...form.querySelectorAll('[name="item_gst_free"]')].map((el) => (el.checked ? "on" : ""));
  return descriptions.map((description, i) => ({
    description,
    amount: amounts[i],
    qty: quantities[i],
    gst_free: gstFlags[i] === "on",
  }));
}

function totalsHtml(gstReg, taxable, gstFree, gst, total) {
  if (!gstReg) return `<div class="preview-row"><span>Total</span><strong>${formatMoney(total)}</strong></div>`;
  let html = "";
  if (taxable > 0 && gstFree > 0) {
    html += `<div class="preview-row"><span>Taxable ex GST</span><span>${formatMoney(taxable)}</span></div>`;
    html += `<div class="preview-row"><span>GST-free ex GST</span><span>${formatMoney(gstFree)}</span></div>`;
  }
  html += `<div class="preview-row"><span>GST (10%)</span><span>${formatMoney(gst)}</span></div>`;
  html += `<div class="preview-row"><span>Total inc GST</span><strong>${formatMoney(total)}</strong></div>`;
  return html;
}

async function renderPreview(panel, ctx) {
  if (!draft) return router.navigate("invoices", "create");
  const [businesses, customers] = await Promise.all([cache.getBusinesses(), cache.getCustomers()]);
  const biz = businesses[draft.business_name] || {};
  const cust = customers[draft.customer_name] || {};
  const gstReg = draft.gst_registered;

  panel.innerHTML = `
    <section class="panel">
      <h2>${gstReg ? "Tax invoice" : "Invoice"} preview</h2>
      <div class="preview-section">
        <div class="preview-row"><span class="preview-label">Invoice #</span><span>${formatInvoiceNumber(draft.invoice_number)}</span></div>
        <div class="preview-row"><span class="preview-label">Date</span><span>${formatInvoiceDate(draft.invoice_date)}</span></div>
        <div class="preview-row"><span class="preview-label">Due</span><span>${formatInvoiceDate(draft.due_date)}</span></div>
        <div class="preview-row"><span class="preview-label">From</span><span>${esc(biz.business_name || draft.business_name)}</span></div>
        <div class="preview-row"><span class="preview-label">To</span><span>${esc(draft.customer_name)}</span></div>
      </div>
      <h3>Items</h3>
      <div class="preview-section">
        ${draft.line_items.map((i) => `<div class="preview-row"><span>${esc(i.description)}${i.quantity !== 1 ? ` × ${i.quantity}` : ""}</span><span>${formatMoney(i.amount_ex_gst)}</span></div>`).join("")}
      </div>
      ${totalsHtml(gstReg, Number(draft.taxable_ex_gst), Number(draft.gst_free_ex_gst), Number(draft.gst_amount), Number(draft.total_inc_gst))}
      ${draft.comment ? `<p class="hint"><strong>Notes:</strong> ${esc(draft.comment)}</p>` : ""}
      <div class="btn-row">
        <button type="button" class="btn primary" id="confirm-invoice">Generate invoice</button>
        <button type="button" class="btn secondary" id="back-edit">Back to edit</button>
      </div>
    </section>`;

  panel.querySelector("#back-edit")?.addEventListener("click", () => router.navigate("invoices", "create"));
  panel.querySelector("#confirm-invoice")?.addEventListener("click", async () => {
    try {
      await createInvoiceOffline({ ...draft });
      await bumpInvoiceCounter(draft.business_name, draft.invoice_number);
      await flushQueue(ctx.onSyncStatus);
      draft = null;
      router.navigate("invoices");
      const { renderInvoices } = await import("./invoices.js");
      await renderInvoices(document.getElementById("tab-invoices"), ctx);
    } catch (ex) {
      alert(ex.message);
    }
  });
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}
