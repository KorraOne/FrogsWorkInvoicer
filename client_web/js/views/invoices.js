import { cache } from "../idb.js";
import {
  createInvoiceOffline,
  bumpInvoiceCounter,
  flushQueue,
  queueEmailSend,
  updateInvoiceStatus,
  softDeleteInvoice,
} from "../sync.js";
import { api } from "../api.js";
import {
  invoicesByStatus,
  filterInvoices,
  statusLabel,
  isInvoiceDeleted,
} from "../domain/invoices_group.js";
import { dueCountdownForInvoice } from "../domain/due_dates.js";
import { lineItemsSummary } from "../domain/gst.js";
import {
  formatMoney,
  formatInvoiceNumber,
  formatInvoiceDate,
} from "../domain/invoice_format.js";
import { router } from "../router.js";
import { renderInvoiceCreate } from "./invoice_form.js";

let filterState = {};

export async function renderInvoices(panel, ctx) {
  if (router.sub === "create" || router.sub === "preview") {
    return renderInvoiceCreate(panel, ctx);
  }

  const [invoices, customers, businesses, settings] = await Promise.all([
    cache.getInvoices(),
    cache.getCustomers(),
    cache.getBusinesses(),
    cache.getSettings(),
  ]);

  const filtered = filterInvoices(invoices, filterState);
  const filteredMap = Object.fromEntries(filtered.map((inv) => [String(inv.invoice_number).padStart(8, "0"), inv]));
  const { groups, sentTotal } = invoicesByStatus(filteredMap, settings);
  const multiBiz = Object.keys(businesses).length > 1;
  const customerNames = Object.keys(customers).sort();
  const businessNames = Object.keys(businesses).sort();

  panel.innerHTML = `
    <div class="panel-header">
      <h2>Past invoices</h2>
      <button type="button" class="btn small primary" id="new-invoice">Create</button>
    </div>
    <form id="invoice-filters" class="panel filters-panel">
      <div class="field"><label>Search</label><input name="q" value="${esc(filterState.q || "")}" placeholder="Number, customer, description"></div>
      <div class="field-row">
        <div class="field"><label>Status</label>
          <select name="status">
            <option value="">All</option>
            <option value="not_sent" ${filterState.status === "not_sent" ? "selected" : ""}>Not sent</option>
            <option value="sent" ${filterState.status === "sent" ? "selected" : ""}>Sent</option>
            <option value="paid" ${filterState.status === "paid" ? "selected" : ""}>Paid</option>
          </select></div>
        <div class="field"><label>Customer</label>
          <select name="customer"><option value="">All</option>
            ${customerNames.map((n) => `<option value="${esc(n)}" ${filterState.customer === n ? "selected" : ""}>${esc(n)}</option>`).join("")}
          </select></div>
      </div>
      ${multiBiz ? `<div class="field"><label>Business</label><select name="business"><option value="">All</option>${businessNames.map((n) => `<option value="${esc(n)}" ${filterState.business === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>` : ""}
      <div class="field-row">
        <div class="field"><label>From</label><input type="date" name="from" value="${filterState.from || ""}"></div>
        <div class="field"><label>To</label><input type="date" name="to" value="${filterState.to || ""}"></div>
      </div>
      <div class="btn-row">
        <button type="submit" class="btn small secondary">Apply filters</button>
        <button type="button" class="btn small ghost" id="clear-filters">Clear</button>
      </div>
    </form>
    ${renderGroup("Not sent yet", "not_sent", groups.not_sent, settings, multiBiz, ctx)}
    ${renderGroup(`Sent, awaiting payment (${formatMoney(sentTotal)} owing)`, "sent", groups.sent, settings, multiBiz, ctx)}
    ${renderGroup("Paid", "paid", groups.paid, settings, multiBiz, ctx)}`;

  panel.querySelector("#new-invoice")?.addEventListener("click", () => router.navigate("invoices", "create"));
  panel.querySelector("#invoice-filters").addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    filterState = Object.fromEntries(fd.entries());
    renderInvoices(panel, ctx);
  });
  panel.querySelector("#clear-filters")?.addEventListener("click", () => {
    filterState = {};
    renderInvoices(panel, ctx);
  });
  wireInvoiceActions(panel, ctx);
}

function renderGroup(title, key, items, settings, multiBiz, ctx) {
  if (!items.length) return `<details class="invoice-group"><summary>${title} (0)</summary><p class="hint">None</p></details>`;
  return `<details class="invoice-group" ${key !== "paid" ? "open" : ""}>
    <summary>${title} (${items.length})</summary>
    ${items.map((inv) => invoiceCard(inv, settings, multiBiz)).join("")}
  </details>`;
}

function invoiceCard(inv, settings, multiBiz) {
  const n = inv.invoice_number;
  const countdown = inv.status === "sent" ? dueCountdownForInvoice(inv, new Date(), settings) : null;
  const canSend = ["not_sent", "send_failed"].includes(inv.status);
  return `<article class="card" data-inv="${n}">
    <div class="card-top">
      <strong>#${formatInvoiceNumber(n)}</strong>
      <span class="badge badge-${inv.status}">${statusLabel(inv.status)}</span>
    </div>
    <div class="meta">${formatInvoiceDate(inv.invoice_date)} · ${esc(inv.customer_name || "")}</div>
    ${multiBiz && inv.business_name ? `<div class="meta">From: ${esc(inv.business_name)}</div>` : ""}
    <div class="meta">${formatMoney(inv.total_inc_gst)} · ${esc(lineItemsSummary(inv))}</div>
    ${countdown ? `<div class="meta countdown-${countdown.kind}">${countdown.label} (${countdown.due_date_fmt})</div>` : ""}
    <div class="actions">
      ${canSend ? `<button class="btn small primary" data-action="send" data-n="${n}">Send</button>` : ""}
      ${inv.status === "sent" ? `<button class="btn small primary" data-action="paid" data-n="${n}">Mark paid</button>` : ""}
      <button class="btn small secondary" data-action="pdf" data-n="${n}">View PDF</button>
      <select class="btn small ghost status-select" data-n="${n}">
        <option value="">Move to…</option>
        <option value="not_sent">Not sent</option>
        <option value="sent">Sent</option>
        <option value="paid">Paid</option>
      </select>
      <button class="btn small danger" data-action="delete" data-n="${n}">Remove</button>
    </div>
  </article>`;
}

function wireInvoiceActions(panel, ctx) {
  panel.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const n = Number(btn.dataset.n);
      const action = btn.dataset.action;
      btn.disabled = true;
      try {
        if (action === "send") {
          await queueEmailSend(n);
          await flushQueue(ctx.onSyncStatus);
        } else if (action === "paid") {
          await updateInvoiceStatus(n, "paid");
          await flushQueue(ctx.onSyncStatus);
        } else if (action === "pdf") {
          const data = await api.getInvoicePdf(n);
          const bytes = Uint8Array.from(atob(data.content_b64), (c) => c.charCodeAt(0));
          const blob = new Blob([bytes], { type: "application/pdf" });
          window.open(URL.createObjectURL(blob), "_blank");
        } else if (action === "delete") {
          if (!confirm("Remove this invoice?")) return;
          await softDeleteInvoice(n);
          await flushQueue(ctx.onSyncStatus);
        }
        await renderInvoices(panel, ctx);
      } catch (ex) {
        alert(ex.message);
      } finally {
        btn.disabled = false;
      }
    });
  });
  panel.querySelectorAll(".status-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      if (!sel.value) return;
      const n = Number(sel.dataset.n);
      try {
        await updateInvoiceStatus(n, sel.value);
        await flushQueue(ctx.onSyncStatus);
        await renderInvoices(panel, ctx);
      } catch (ex) {
        alert(ex.message);
      }
    });
  });
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}
