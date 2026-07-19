import { fetchInvoicePdf } from "../api/mobile";
import {
  disclosureBlockHtml,
  dueRuleFieldsHtml,
  formSectionHtml,
  wireDisclosure,
  wireDueRuleToggles,
} from "../components/forms";
import {
  collapsedDueSummaryText,
  dueCountdownForInvoice,
  duePrefsForNewInvoice,
  dueRuleFromFormData,
  invoiceDueSummary,
} from "../domain/dueDates";
import { confirmSheet, emptyStateHtml, openSheet, showToast, wireSheetGrabDismiss } from "../components/ui";
import { trackEvent } from "../lib/analytics";
import { cache } from "../data/idb";
import {
  flushQueue,
  newInvoiceId,
  pullBootstrap,
  queueEmailSend,
  reconcileEmailSendStatus,
  saveInvoicePackage,
  softDeleteInvoice,
  updateInvoiceStatus,
  upsertCustomer,
} from "../data/sync";
import {
  addressFieldsHtml,
  normalizeAbn,
  normalizeAuAddress,
  readAddressFromForm,
} from "../domain/address";
import {
  anyBusinessGstRegistered,
  lineItemsSummary,
  parseLineItems,
} from "../domain/gst";
import {
  formatInvoiceDate,
  formatInvoiceNumber,
  formatMoney,
  moneyStr,
  parseInvoiceNumberInput,
  suggestedInvoiceNumber,
  todayIso,
} from "../domain/invoiceFormat";
import {
  findInvoiceNumberConflicts,
  invoiceStorageKey,
} from "../domain/invoiceIdentity";
import {
  openQuotesFiltered,
  registerInvoiceListFilter,
} from "../domain/crossDocNav";
import {
  countActiveFilters,
  filterInvoices,
  invoicesByStatus,
  statusLabel,
  type InvoiceFilters,
} from "../domain/invoicesGroup";
import { esc } from "../lib/escape";
import { filesToWorkPhotos } from "../lib/images";
import { router } from "../router";
import type { AppContext } from "../types";

let filterState: InvoiceFilters = {};
let draft: Record<string, unknown> | null = null;
let draftPhotos: string[] = [];
let filtersOpen = false;
/** One-off customers for the current create flow (not persisted to customers list). */
let ephemeralCustomers: Record<string, Record<string, unknown>> = {};
/** Blob URL for the success-screen PDF embed; revoke on leave. */
let successPdfUrl: string | null = null;

type DraftLine = {
  id: string;
  description: string;
  qty: string;
  amount: string;
  gst_applicable: boolean;
};

let draftLines: DraftLine[] = [];

export function openInvoicesFiltered(q: string) {
  filterState = { q: String(q || "").trim() };
  filtersOpen = true;
  router.navigate("invoices");
}

registerInvoiceListFilter((q) => {
  filterState = { q };
  filtersOpen = true;
});

function newDraftLineId(): string {
  return `line_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function clearCreateDraft() {
  draft = null;
  draftPhotos = [];
  draftLines = [];
  ephemeralCustomers = {};
}

function revokeSuccessPdfUrl() {
  if (successPdfUrl) {
    URL.revokeObjectURL(successPdfUrl);
    successPdfUrl = null;
  }
}

/** Persist live create-form fields into `draft` before a remount (e.g. after photos). */
function captureCreateFormState(panel: HTMLElement) {
  const form = panel.querySelector("#create-invoice-form") as HTMLFormElement | null;
  if (!form) return;
  const fd = new FormData(form);
  const customerName = String(fd.get("customer") || "").trim();
  const businessName = String(fd.get("business") || "").trim();
  draft = {
    ...(draft || {}),
    customer_name: customerName || draft?.customer_name || "",
    business_name: businessName || draft?.business_name || "",
    invoice_number: String(fd.get("invoice_number") || draft?.invoice_number || "").trim(),
    invoice_date: String(fd.get("invoice_date") || draft?.invoice_date || "").trim(),
    due_rule_type: String(fd.get("due_rule_type") || draft?.due_rule_type || "").trim(),
    due_net_days: Number(fd.get("due_net_days") ?? draft?.due_net_days ?? 7),
    due_fixed_date: String(fd.get("due_fixed_date") || draft?.due_fixed_date || "").trim(),
    comment: String(fd.get("comment") || "").trim(),
  };
}

function loadInvoiceIntoCreateDraft(inv: Record<string, unknown>) {
  draft = { ...inv };
  draftPhotos = [...((inv.work_photos_b64 as string[]) || [])];
  const items = (inv.line_items as Array<Record<string, unknown>> | undefined) || [];
  draftLines = items.map((item) => ({
    id: newDraftLineId(),
    description: String(item.description || ""),
    qty: String(item.quantity ?? "1"),
    amount: String(item.unit_amount_ex_gst ?? ""),
    gst_applicable: item.gst_applicable !== false,
  }));
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchPdfBlob(
  invoiceId: string
): Promise<{ blob: Blob; filename: string; url: string }> {
  const key = String(invoiceId || "").trim();
  let lastErr: unknown;
  for (let attempt = 0; attempt < 8; attempt++) {
    if (attempt > 0) await sleep(700);
    try {
      if (attempt > 0) {
        try {
          await pullBootstrap();
        } catch {
          /* fetch may still generate */
        }
      }
      const data = await fetchInvoicePdf(key);
      const binary = atob(data.content_b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: "application/pdf" });
      const filename = String(data.filename || `Invoice_${key}.pdf`).trim() || "invoice.pdf";
      const url = URL.createObjectURL(blob);
      return { blob, filename, url };
    } catch (ex) {
      lastErr = ex;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("PDF not ready.");
}

function downloadPdf(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "invoice.pdf";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function openPdf(invoiceId: string) {
  const { url, filename } = await fetchPdfBlob(invoiceId);
  try {
    downloadPdf(url, filename);
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}

function customerFilterNames(
  customers: Record<string, Record<string, unknown>>,
  invoices: Record<string, Record<string, unknown>>
): string[] {
  const names = new Set(Object.keys(customers));
  for (const inv of Object.values(invoices)) {
    if (inv.deleted_at) continue;
    const n = String(inv.customer_name || "").trim();
    if (n) names.add(n);
  }
  return [...names].sort();
}

function resolveCustomerProfile(
  name: string,
  customers: Record<string, Record<string, unknown>>
): Record<string, unknown> {
  return customers[name] || ephemeralCustomers[name] || {};
}

function snapshotCustomerOntoInvoice(
  customerName: string,
  profile: Record<string, unknown>
): Record<string, unknown> {
  return {
    customer_name: customerName,
    customer_email: String(profile.email || "").trim(),
    customer_abn: String(profile.abn || "").trim(),
    address_line1: String(profile.address_line1 || "").trim(),
    address_line2: String(profile.address_line2 || "").trim(),
    suburb: String(profile.suburb || "").trim(),
    state: String(profile.state || "").trim(),
    postcode: String(profile.postcode || "").trim(),
  };
}

function draftLineAmount(line: DraftLine): number | null {
  const qty = Number(String(line.qty || "1").replace(/,/g, "")) || 0;
  const unit = Number(String(line.amount || "").replace(/\$/g, "").replace(/,/g, ""));
  if (!Number.isFinite(unit) || String(line.amount || "").trim() === "") return null;
  return Math.round((qty * unit + Number.EPSILON) * 100) / 100;
}

function readDraftLineRows(gstReg: boolean) {
  return draftLines.map((line) => ({
    description: line.description,
    amount: line.amount,
    qty: line.qty,
    gst_free: gstReg ? !line.gst_applicable : false,
  }));
}

export async function renderInvoices(panel: HTMLElement, ctx: AppContext): Promise<void> {
  if (router.sub === "create") return renderCreate(panel, ctx);
  if (router.sub === "success") return renderSuccess(panel, ctx);

  const [invoices, customers, businesses, settings, quotes] = await Promise.all([
    cache.getInvoices(),
    cache.getCustomers(),
    cache.getBusinesses(),
    cache.getSettings(),
    cache.getQuotes(),
  ]);

  const filtered = filterInvoices(invoices, filterState);
  const filteredMap = Object.fromEntries(
    filtered.map((inv) => [invoiceStorageKey(inv), inv])
  );
  const { groups, sentTotal } = invoicesByStatus(filteredMap, settings);
  const multiBiz = Object.keys(businesses).length > 1;
  const customerNames = customerFilterNames(customers, invoices);
  const businessNames = Object.keys(businesses).sort();
  const activeFilterCount = countActiveFilters(filterState);
  const totalCount =
    groups.not_sent.length + groups.sent.length + groups.paid.length;

  panel.innerHTML = `
    <div class="panel-header">
      <h2>Past invoices</h2>
      <button type="button" class="btn small primary" id="new-invoice">Create</button>
    </div>
    <button type="button" class="btn small secondary filters-toggle" id="toggle-filters">
      Filters${activeFilterCount ? ` · ${activeFilterCount} active` : ""} ▾
    </button>
    <form id="invoice-filters" class="panel filters-panel" ${filtersOpen ? "" : "hidden"}>
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
            ${customerNames
              .map(
                (n) =>
                  `<option value="${esc(n)}" ${filterState.customer === n ? "selected" : ""}>${esc(n)}</option>`
              )
              .join("")}
          </select></div>
      </div>
      ${
        multiBiz
          ? `<div class="field"><label>Business</label><select name="business"><option value="">All</option>${businessNames
              .map(
                (n) =>
                  `<option value="${esc(n)}" ${filterState.business === n ? "selected" : ""}>${esc(n)}</option>`
              )
              .join("")}</select></div>`
          : ""
      }
      <div class="field-row">
        <div class="field"><label>From</label><input type="date" name="from" value="${filterState.from || ""}"></div>
        <div class="field"><label>To</label><input type="date" name="to" value="${filterState.to || ""}"></div>
      </div>
      <div class="btn-row">
        <button type="submit" class="btn small secondary">Apply filters</button>
        <button type="button" class="btn small ghost" id="clear-filters">Clear</button>
      </div>
    </form>
    ${
      totalCount
        ? `${renderGroup("Not sent yet", "not_sent", groups.not_sent, settings, multiBiz, quotes, activeFilterCount > 0)}
           ${renderGroup(`Sent, awaiting payment (${formatMoney(sentTotal)} owing)`, "sent", groups.sent, settings, multiBiz, quotes, activeFilterCount > 0)}
           ${renderGroup("Paid", "paid", groups.paid, settings, multiBiz, quotes, activeFilterCount > 0)}`
        : emptyStateHtml(
            "No invoices yet",
            "Create a sales invoice for a customer.",
            "empty-create",
            "Create sales invoice"
          )
    }`;

  panel.querySelector("#new-invoice")?.addEventListener("click", () =>
    router.navigate("invoices", "create")
  );
  panel.querySelector("#empty-create")?.addEventListener("click", () =>
    router.navigate("invoices", "create")
  );
  panel.querySelector("#toggle-filters")?.addEventListener("click", () => {
    filtersOpen = !filtersOpen;
    renderInvoices(panel, ctx);
  });
  panel.querySelector("#invoice-filters")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    filterState = Object.fromEntries(fd.entries()) as InvoiceFilters;
    renderInvoices(panel, ctx);
  });
  panel.querySelector("#clear-filters")?.addEventListener("click", () => {
    filterState = {};
    renderInvoices(panel, ctx);
  });
  wireListActions(panel, ctx, customers);
}

function searchQFromNumber(raw: unknown): string {
  const n = parseInt(String(raw ?? ""), 10);
  return Number.isFinite(n) && n > 0 ? String(n) : String(raw || "").trim();
}

function sourceQuoteMeta(
  inv: Record<string, unknown>,
  quotes: Record<string, Record<string, unknown>>
): string {
  const id = String(inv.source_quote_id || "").trim();
  let num = inv.source_quote_number;
  let sourceQuote = id && quotes[id] && !quotes[id].deleted_at ? quotes[id] : null;

  if (!sourceQuote) {
    // Older converts only stored the link on the quote side; reverse-lookup by
    // converted_invoice_id / converted_invoice_number.
    const invKey = invoiceStorageKey(inv);
    const invNum = Number(inv.invoice_number);
    sourceQuote =
      Object.values(quotes).find(
        (q) =>
          !q.deleted_at &&
          String(q.status || "") === "converted" &&
          (String(q.converted_invoice_id || "") === invKey ||
            (q.converted_invoice_number != null &&
              Number(q.converted_invoice_number) === invNum))
      ) || null;
  }

  if (sourceQuote) {
    num = sourceQuote.quote_number;
  } else if (num == null || num === "") {
    return id ? `<div class="meta">From quote (removed)</div>` : "";
  }

  if (num == null || num === "") return "";
  const display = formatInvoiceNumber(num as string | number);
  const q = searchQFromNumber(num);
  if (sourceQuote && q) {
    return `<div class="meta"><button type="button" class="meta-link" data-action="goto-quote" data-q="${esc(q)}">From quote #${display} ›</button></div>`;
  }
  return `<div class="meta">From quote #${display}</div>`;
}

function renderGroup(
  title: string,
  key: string,
  items: Record<string, unknown>[],
  settings: Record<string, unknown>,
  multiBiz: boolean,
  quotes: Record<string, Record<string, unknown>>,
  forceOpen = false
) {
  if (!items.length) {
    return `<details class="invoice-group"><summary>${title} (0)</summary><p class="hint">None</p></details>`;
  }
  const open = forceOpen || key !== "paid";
  return `<details class="invoice-group" ${open ? "open" : ""}>
    <summary>${title} (${items.length})</summary>
    ${items.map((inv) => invoiceCard(inv, settings, multiBiz, quotes)).join("")}
  </details>`;
}

function invoiceCard(
  inv: Record<string, unknown>,
  settings: Record<string, unknown>,
  multiBiz: boolean,
  quotes: Record<string, Record<string, unknown>>
) {
  const n = Number(inv.invoice_number);
  const id = esc(invoiceStorageKey(inv));
  const status = String(inv.status || "not_sent");
  const countdown =
    status === "sent" ? dueCountdownForInvoice(inv, new Date(), settings) : null;
  const canSend = ["not_sent", "send_failed"].includes(status);
  return `<article class="card" data-inv="${id}">
    <div class="card-top">
      <strong>#${formatInvoiceNumber(n)}</strong>
      <span class="badge badge-${status}">${statusLabel(status)}</span>
    </div>
    <div class="meta">${formatInvoiceDate(String(inv.invoice_date || ""))} · ${esc(String(inv.customer_name || ""))}</div>
    ${multiBiz && inv.business_name ? `<div class="meta">From: ${esc(String(inv.business_name))}</div>` : ""}
    <div class="meta">${formatMoney(Number(inv.total_inc_gst || 0))} · ${esc(lineItemsSummary(inv))}</div>
    ${
      countdown
        ? `<div class="meta countdown-${countdown.kind}">${countdown.label} (${countdown.due_date_fmt})</div>`
        : ""
    }
    ${sourceQuoteMeta(inv, quotes)}
    <div class="actions">
      ${canSend ? `<button class="btn small primary" data-action="send" data-id="${id}">Send</button>` : ""}
      ${status === "sent" ? `<button class="btn small primary" data-action="paid" data-id="${id}">Mark paid</button>` : ""}
      <button class="btn small secondary" data-action="pdf" data-id="${id}">View PDF</button>
      <button class="btn small ghost" data-action="more" data-id="${id}" data-n="${n}" aria-label="More actions">···</button>
    </div>
  </article>`;
}

/** Re-paint invoice list after async email status lands in cache. */
async function refreshInvoicesListIfVisible(ctx: AppContext) {
  if (router.tab !== "invoices" || router.sub) return;
  const listPanel = document.getElementById("tab-invoices") as HTMLElement | null;
  if (!listPanel) return;
  await renderInvoices(listPanel, ctx);
}

function wireListActions(
  panel: HTMLElement,
  ctx: AppContext,
  customers: Record<string, Record<string, unknown>>
) {
  panel.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const action = el.dataset.action;
      const id = String(el.dataset.id || "").trim();
      const n = Number(el.dataset.n);
      try {
        if (action === "send") {
          showToast("Sending…", "success");
          const sendResult = await queueEmailSend(id);
          trackEvent("send_invoice");
          await flushQueue(ctx.onSyncStatus);
          if (sendResult.finalStatus === "sent") {
            showToast("Invoice sent.", "success");
          } else if (sendResult.finalStatus === "send_failed") {
            showToast("Send failed. Check the customer email and try again.", "error");
          } else {
            void reconcileEmailSendStatus(id).then(async (status) => {
              if (status === "sent") showToast("Invoice sent.", "success");
              else if (status === "send_failed") {
                showToast("Send failed. Check the customer email and try again.", "error");
              }
              await refreshInvoicesListIfVisible(ctx);
            });
          }
        } else if (action === "paid") {
          await updateInvoiceStatus(id, "paid");
          await flushQueue(ctx.onSyncStatus);
          showToast("Marked as paid.", "success");
        } else if (action === "pdf") {
          await openPdf(id);
        } else if (action === "goto-quote") {
          const q = String(el.dataset.q || "").trim();
          if (q) openQuotesFiltered(q);
          return;
        } else if (action === "more") {
          await handleMoreActions(panel, ctx, id, n, customers);
          return;
        }
        await renderInvoices(panel, ctx);
      } catch (ex) {
        showToast(ex instanceof Error ? ex.message : "Action failed.", "error");
      }
    });
  });
}

async function handleMoreActions(
  panel: HTMLElement,
  ctx: AppContext,
  invoiceId: string,
  n: number,
  _customers: Record<string, Record<string, unknown>>
) {
  const choice = await openSheet({
    title: `#${formatInvoiceNumber(n)}`,
    bodyHtml: `<p class="hint">Move status or remove this invoice.</p>`,
    actions: [
      { id: "not_sent", label: "Move to Not sent", className: "btn secondary" },
      { id: "sent", label: "Move to Sent", className: "btn secondary" },
      { id: "paid", label: "Move to Paid", className: "btn secondary" },
      { id: "delete", label: "Remove", className: "btn danger" },
      { id: "cancel", label: "Cancel", className: "btn ghost" },
    ],
  });
  if (!choice || choice === "cancel") return;
  try {
    if (choice === "delete") {
      const ok = await confirmSheet(`Remove invoice #${formatInvoiceNumber(n)}?`, "Remove");
      if (!ok) return;
      await softDeleteInvoice(invoiceId);
      await flushQueue(ctx.onSyncStatus);
      showToast("Invoice removed.", "success");
    } else {
      await updateInvoiceStatus(invoiceId, choice);
      await flushQueue(ctx.onSyncStatus);
      showToast(`Moved to ${statusLabel(choice)}.`, "success");
    }
    await renderInvoices(panel, ctx);
  } catch (ex) {
    showToast(ex instanceof Error ? ex.message : "Action failed.", "error");
  }
}

async function renderCreate(panel: HTMLElement, ctx: AppContext) {
  const [businesses, customers, invoices, settings] = await Promise.all([
    cache.getBusinesses(),
    cache.getCustomers(),
    cache.getInvoices(),
    cache.getSettings(),
  ]);
  const bizNames = Object.keys(businesses);
  const defaultBiz =
    settings.default_business && businesses[String(settings.default_business)]
      ? String(settings.default_business)
      : bizNames[0] || "";
  const restoring = Boolean(draft?.customer_name || draft?.invoice_number);
  const selectedBiz =
    restoring && draft?.business_name && businesses[String(draft.business_name)]
      ? String(draft.business_name)
      : defaultBiz;
  const biz = businesses[selectedBiz] || {};
  const gstReg = anyBusinessGstRegistered(businesses);
  const suggested = suggestedInvoiceNumber(selectedBiz, biz, invoices);
  const selectedCustomer = restoring ? String(draft?.customer_name || "") : "";
  const invoiceNumberValue = restoring
    ? String(draft?.invoice_number ?? suggested)
    : String(suggested);
  const invoiceDateValue = restoring
    ? String(draft?.invoice_date || todayIso())
    : todayIso();
  const duePrefs = restoring
    ? {
        due_rule_type: String(draft?.due_rule_type || "net_days"),
        due_net_days: Number(draft?.due_net_days ?? 7),
        due_fixed_date: String(draft?.due_fixed_date || ""),
      }
    : duePrefsForNewInvoice(settings, todayIso());
  const dueSummary0 = invoiceDueSummary(
    invoiceDateValue,
    duePrefs.due_rule_type,
    duePrefs.due_net_days,
    duePrefs.due_fixed_date
  );
  // Ensure one-off customers from the draft stay selectable after edit → create
  if (selectedCustomer && !customers[selectedCustomer] && !ephemeralCustomers[selectedCustomer]) {
    ephemeralCustomers[selectedCustomer] = {
      email: draft?.customer_email || "",
      abn: draft?.customer_abn || "",
      address_line1: draft?.address_line1 || "",
      address_line2: draft?.address_line2 || "",
      suburb: draft?.suburb || "",
      state: draft?.state || "",
      postcode: draft?.postcode || "",
    };
  }
  const custNames = [
    ...new Set([...Object.keys(customers), ...Object.keys(ephemeralCustomers)]),
  ].sort();
  const invNumDisplay = formatInvoiceNumber(
    Number(invoiceNumberValue) || invoiceNumberValue
  );
  const dateDisplay = formatInvoiceDate(invoiceDateValue);

  const photoThumbs = draftPhotos
    .map(
      (src, i) =>
        `<div class="photo-thumb"><img src="${src}" alt="Work photo ${i + 1}"><button type="button" class="btn small ghost remove-photo" data-i="${i}">×</button></div>`
    )
    .join("");

  const dueSummaryText = collapsedDueSummaryText(
    duePrefs.due_rule_type,
    duePrefs.due_net_days,
    duePrefs.due_fixed_date,
    dueSummary0.due_date_fmt
  );

  const detailsBody = `
      ${
        bizNames.length > 1
          ? `<div class="field"><label>From</label><select name="business">${bizNames
              .map(
                (n) =>
                  `<option value="${esc(n)}" ${n === selectedBiz ? "selected" : ""}>${esc(n)}</option>`
              )
              .join("")}</select></div>`
          : `<input type="hidden" name="business" value="${esc(selectedBiz)}">`
      }
      <div class="inv-meta-row">
        <div class="inv-meta-number">
          <button type="button" class="inv-num-btn" id="inv-num-toggle" aria-expanded="false">
            <strong id="inv-num-label">Invoice #${esc(String(invNumDisplay))}</strong>
            <span class="inv-num-hint">Change</span>
          </button>
        </div>
        <div class="inv-meta-date">
          <span class="inv-date-label">Date</span>
          <span class="inv-date-value">${esc(dateDisplay)}</span>
          <input type="hidden" name="invoice_date" value="${esc(invoiceDateValue)}">
        </div>
      </div>
      <div class="inv-num-edit" id="inv-num-edit" hidden>
        <div class="field"><label for="invoice_number_input">Invoice number</label>
          <input name="invoice_number" id="invoice_number_input" value="${esc(invoiceNumberValue)}" inputmode="numeric"></div>
      </div>
      <p class="hint error-text" id="invoice-number-warn" hidden></p>
      <input type="hidden" name="invoice_number_default" value="${esc(String(suggested))}">`;

  const customerBody = `
      <div class="field-row align-end customer-pick-row">
        <div class="field flex-2 customer-select-field">
          <label class="sr-only" for="customer-select">Customer</label>
          <select name="customer" id="customer-select" required>
            <option value="">Select customer</option>
            ${custNames
              .map(
                (n) =>
                  `<option value="${esc(n)}" ${n === selectedCustomer ? "selected" : ""}>${esc(n)}</option>`
              )
              .join("")}
          </select>
        </div>
        <button type="button" class="btn small secondary" id="add-customer-inline">+ Add</button>
      </div>`;

  const linesBody = `
      <div id="line-items" class="line-items-stack"></div>
      <button type="button" class="btn small ghost" id="add-line">+ Add line</button>`;

  const notesBody = `<div class="field"><label>Notes (optional)</label><textarea name="comment" rows="2" placeholder="Shown on the invoice">${esc(draft?.comment || "")}</textarea></div>`;

  const photosBody = `
      <p class="hint">Optional, max 6</p>
      <input type="file" id="work-photos" class="sr-only" accept="image/*" multiple>
      <button type="button" class="btn small secondary" id="add-photos-btn">Add photos</button>
      <div class="photo-grid" id="photo-grid">${photoThumbs}</div>
      <p class="hint">${draftPhotos.length}/6 photos</p>`;

  panel.innerHTML = `
    <form id="create-invoice-form" class="panel" novalidate>
      <div class="panel-header">
        <h2>Create sales invoice</h2>
        <button type="button" class="btn small ghost" id="cancel-create">Cancel</button>
      </div>
      ${formSectionHtml("Invoice details", detailsBody)}
      ${formSectionHtml("Customer", customerBody)}
      ${formSectionHtml("Line items", linesBody)}
      ${formSectionHtml(
        "Payment due",
        disclosureBlockHtml({
          id: "due-disclosure",
          summaryHtml: `<span id="due-summary-text">${esc(dueSummaryText)}</span>`,
          bodyHtml: dueRuleFieldsHtml(duePrefs, { showFixed: true }),
          defaultOpen: false,
          toggleLabel: "Adjust",
          toggleLabelOpen: "Done",
        })
      )}
      ${formSectionHtml("Notes", notesBody)}
      ${formSectionHtml("Work photos", photosBody)}
      <div class="preview-section totals-panel" id="live-totals"></div>
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-invoice">Save invoice</button>
      </div>
    </form>`;

  wireDueRuleToggles(panel);
  wireDisclosure(panel, "due-disclosure", { closedLabel: "Adjust", openLabel: "Done" });

  const form = panel.querySelector("#create-invoice-form") as HTMLFormElement;

  const syncInvNumLabel = () => {
    const input = panel.querySelector("#invoice_number_input") as HTMLInputElement | null;
    const label = panel.querySelector("#inv-num-label");
    if (!input || !label) return;
    try {
      label.textContent = `Invoice #${formatInvoiceNumber(parseInvoiceNumberInput(input.value))}`;
    } catch {
      /* keep */
    }
  };

  const setInvNumEditOpen = (open: boolean) => {
    const edit = panel.querySelector("#inv-num-edit") as HTMLElement | null;
    const btn = panel.querySelector("#inv-num-toggle") as HTMLButtonElement | null;
    const hint = panel.querySelector(".inv-num-hint");
    if (edit) edit.hidden = !open;
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (hint) hint.textContent = open ? "Done" : "Change";
    if (!open) {
      const input = panel.querySelector("#invoice_number_input") as HTMLInputElement | null;
      const def = (panel.querySelector('[name="invoice_number_default"]') as HTMLInputElement)
        ?.value;
      if (input && def && !String(input.value || "").trim()) input.value = def;
      syncInvNumLabel();
      refreshNumberWarn();
    }
  };

  panel.querySelector("#inv-num-toggle")?.addEventListener("click", () => {
    const edit = panel.querySelector("#inv-num-edit") as HTMLElement | null;
    setInvNumEditOpen(Boolean(edit?.hidden));
  });

  const refreshNumberWarn = () => {
    const warn = panel.querySelector("#invoice-number-warn") as HTMLElement | null;
    const input = panel.querySelector("#invoice_number_input") as HTMLInputElement | null;
    if (!warn || !input) return;
    try {
      const num = parseInvoiceNumberInput(input.value);
      const bizName = String(new FormData(form).get("business") || selectedBiz);
      const conflicts = findInvoiceNumberConflicts(invoices, num, bizName);
      if (conflicts.active || conflicts.deleted) {
        const parts: string[] = [];
        if (conflicts.active) {
          parts.push(
            `${conflicts.active} active invoice${conflicts.active === 1 ? "" : "s"} already use this number`
          );
        }
        if (conflicts.deleted) {
          parts.push(
            `${conflicts.deleted} removed invoice${conflicts.deleted === 1 ? "" : "s"} used this number`
          );
        }
        warn.textContent = `${parts.join("; ")}. You can still reuse it — a new invoice will be created.`;
        warn.hidden = false;
      } else {
        warn.textContent = "";
        warn.hidden = true;
      }
    } catch {
      warn.textContent = "";
      warn.hidden = true;
    }
  };
  panel.querySelector("#invoice_number_input")?.addEventListener("input", () => {
    syncInvNumLabel();
    refreshNumberWarn();
  });
  form.querySelector('[name="business"]')?.addEventListener("change", () => {
    const bizSelect = form.querySelector('[name="business"]') as HTMLSelectElement | null;
    const bizName = bizSelect?.value || selectedBiz;
    const nextSuggested = suggestedInvoiceNumber(bizName, businesses[bizName] || {}, invoices);
    const defInput = form.querySelector('[name="invoice_number_default"]') as HTMLInputElement | null;
    const numInput = form.querySelector("#invoice_number_input") as HTMLInputElement | null;
    if (defInput) defInput.value = String(nextSuggested);
    if (numInput && String(numInput.value) === String(invoiceNumberValue)) {
      numInput.value = String(nextSuggested);
      syncInvNumLabel();
    }
    refreshNumberWarn();
  });
  refreshNumberWarn();

  const refreshDueSummary = () => {
    const fd = new FormData(form);
    const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
    const invDate = String(fd.get("invoice_date") || todayIso());
    const sum = invoiceDueSummary(invDate, due.due_rule_type, due.due_net_days, due.due_fixed_date);
    const el = panel.querySelector("#due-summary-text");
    if (el) {
      el.textContent = collapsedDueSummaryText(
        due.due_rule_type,
        due.due_net_days,
        due.due_fixed_date,
        sum.due_date_fmt
      );
    }
  };
  form.addEventListener("change", refreshDueSummary);
  form.addEventListener("input", refreshDueSummary);

  const refreshLineList = () => {
    const stack = panel.querySelector("#line-items") as HTMLElement | null;
    if (!stack) return;
    stack.innerHTML = draftLines.map((line, i) => lineSummaryRowHtml(line, i, gstReg)).join("");
    wireLineSummaryList(panel, gstReg, () => {
      refreshLineList();
      updateTotals();
    });
  };

  const updateTotals = () => {
    try {
      const parsed = parseLineItems(readDraftLineRows(gstReg), gstReg);
      (panel.querySelector("#live-totals") as HTMLElement).innerHTML = totalsHtml(
        gstReg,
        parsed.taxableExGst,
        parsed.gstFreeExGst,
        parsed.gstAmount,
        parsed.totalIncGst
      );
    } catch {
      (panel.querySelector("#live-totals") as HTMLElement).innerHTML = "";
    }
  };

  refreshLineList();
  updateTotals();

  panel.querySelector("#add-line")?.addEventListener("click", async () => {
    const saved = await openLineItemSheet({ gstReg });
    if (!saved) return;
    draftLines.push(saved);
    refreshLineList();
    updateTotals();
  });

  panel.querySelector("#cancel-create")?.addEventListener("click", () => {
    clearCreateDraft();
    router.navigate("invoices");
  });

  panel.querySelector("#add-photos-btn")?.addEventListener("click", () => {
    (panel.querySelector("#work-photos") as HTMLInputElement | null)?.click();
  });

  panel.querySelector("#work-photos")?.addEventListener("change", async (e) => {
    const input = e.target as HTMLInputElement;
    if (!input.files?.length) return;
    try {
      captureCreateFormState(panel);
      draftPhotos = await filesToWorkPhotos(input.files, draftPhotos, 6);
      input.value = "";
      await renderCreate(panel, ctx);
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Could not add photo.", "error");
    }
  });

  panel.querySelectorAll(".remove-photo").forEach((btn) => {
    btn.addEventListener("click", () => {
      captureCreateFormState(panel);
      const i = Number((btn as HTMLElement).dataset.i);
      draftPhotos.splice(i, 1);
      renderCreate(panel, ctx);
    });
  });

  panel.querySelector("#add-customer-inline")?.addEventListener("click", async () => {
    await openInlineCustomerSheet(panel, ctx);
  });

  panel.querySelector("#save-invoice")?.addEventListener("click", async () => {
    const err = panel.querySelector("#form-error") as HTMLElement;
    err.hidden = true;
    const saveBtn = panel.querySelector("#save-invoice") as HTMLButtonElement | null;
    if (saveBtn) saveBtn.disabled = true;
    try {
      const fd = new FormData(form);
      const businessName = String(fd.get("business") || selectedBiz);
      const gstRegistered = gstReg;
      const parsed = parseLineItems(readDraftLineRows(gstRegistered), gstRegistered);
      const customerName = String(fd.get("customer") || "").trim();
      if (!customerName) throw new Error("Select a customer.");
      const custProfile = resolveCustomerProfile(customerName, customers);
      const invoiceNumber = parseInvoiceNumberInput(String(fd.get("invoice_number")));
      const due = dueRuleFromFormData(Object.fromEntries(fd.entries()), settings);
      const dueSummary = invoiceDueSummary(
        fd.get("invoice_date") || todayIso(),
        due.due_rule_type,
        due.due_net_days,
        due.due_fixed_date
      );
      const invoiceId = String(draft?.invoice_id || "").trim() || newInvoiceId();
      const toSave: Record<string, unknown> = {
        invoice_id: invoiceId,
        invoice_number: invoiceNumber,
        invoice_date: String(fd.get("invoice_date") || todayIso()),
        ...snapshotCustomerOntoInvoice(customerName, custProfile),
        business_name: businessName,
        line_items: parsed.items,
        description: parsed.items.map((i) => i.description).join("; "),
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
        comment: String(fd.get("comment") || "").trim(),
        work_photos_b64: [...draftPhotos],
        status: String(draft?.status || "not_sent"),
        pdf_status: "pending",
      };
      draft = toSave;
      const savedId = await saveInvoicePackage({
        invoice: toSave,
        businessName,
        usedNumber: invoiceNumber,
        settingsPartial: {
          last_due_rule_type: due.due_rule_type,
          last_due_net_days: due.due_net_days,
          last_due_fixed_date: due.due_fixed_date || "",
        },
        preparePdf: true,
      });
      await flushQueue(ctx.onSyncStatus);
      clearCreateDraft();
      router.navigate("invoices", "success", { name: savedId });
      await renderSuccess(panel, ctx);
    } catch (ex) {
      err.textContent = ex instanceof Error ? ex.message : "Save failed.";
      err.hidden = false;
      if (saveBtn) saveBtn.disabled = false;
    }
  });
}

async function openInlineCustomerSheet(panel: HTMLElement, ctx: AppContext) {
  const result = await new Promise<"saved" | "once" | null>((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "sheet-overlay";
    overlay.innerHTML = `
      <div class="sheet sheet-tall" role="dialog" aria-modal="true">
        <div class="sheet-handle" aria-hidden="true"></div>
        <h3 class="sheet-title">Add customer</h3>
        <form id="inline-customer-form" class="sheet-body" novalidate>
          <div class="field"><label>Name</label><input name="name" required></div>
          <div class="field"><label>Email</label><input name="email" type="email"></div>
          ${addressFieldsHtml("", {})}
          <div class="field"><label>ABN (optional)</label><input name="abn"></div>
          <p class="hint">Save keeps them in Customers. Use once is only for this invoice.</p>
          <p class="error-text" id="inline-cust-error" hidden></p>
        </form>
        <div class="sheet-actions sheet-actions-triple">
          <button type="button" class="btn secondary" data-act="cancel">Cancel</button>
          <button type="button" class="btn secondary" data-act="once">Use once</button>
          <button type="button" class="btn primary" data-act="save">Save</button>
        </div>
      </div>`;
    const sheet = overlay.querySelector(".sheet") as HTMLElement;
    const close = (v: "saved" | "once" | null) => {
      overlay.remove();
      resolve(v);
    };
    wireSheetGrabDismiss(overlay, sheet, () => close(null));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });
    overlay.querySelector('[data-act="cancel"]')?.addEventListener("click", () => close(null));

    const readProfile = () => {
      const form = overlay.querySelector("#inline-customer-form") as HTMLFormElement;
      const fd = new FormData(form);
      const name = String(fd.get("name") || "").trim();
      if (!name) throw new Error("Customer name is required.");
      const email = String(fd.get("email") || "").trim();
      const addr = normalizeAuAddress(readAddressFromForm(fd));
      const abn = fd.get("abn") ? normalizeAbn(String(fd.get("abn"))) : "";
      return { name, profile: { email, ...addr, abn, created_via: "inline" } as Record<string, unknown> };
    };

    overlay.querySelector('[data-act="once"]')?.addEventListener("click", () => {
      const err = overlay.querySelector("#inline-cust-error") as HTMLElement;
      err.hidden = true;
      try {
        const { name, profile } = readProfile();
        ephemeralCustomers[name] = profile;
        draft = draft || {};
        (draft as Record<string, unknown>)._preselectCustomer = name;
        close("once");
      } catch (ex) {
        err.textContent = ex instanceof Error ? ex.message : "Invalid details.";
        err.hidden = false;
      }
    });

    overlay.querySelector('[data-act="save"]')?.addEventListener("click", async () => {
      const err = overlay.querySelector("#inline-cust-error") as HTMLElement;
      err.hidden = true;
      try {
        const { name, profile } = readProfile();
        await upsertCustomer(name, profile);
        await flushQueue(ctx.onSyncStatus);
        delete ephemeralCustomers[name];
        draft = draft || {};
        (draft as Record<string, unknown>)._preselectCustomer = name;
        close("saved");
      } catch (ex) {
        err.textContent = ex instanceof Error ? ex.message : "Save failed.";
        err.hidden = false;
      }
    });
    document.body.appendChild(overlay);
  });

  if (result === "saved" || result === "once") {
    showToast(result === "saved" ? "Customer saved." : "Customer added for this invoice.", "success");
    captureCreateFormState(panel);
    const pre = String((draft as Record<string, unknown> | null)?._preselectCustomer || "");
    if (pre && draft) {
      draft.customer_name = pre;
      delete (draft as Record<string, unknown>)._preselectCustomer;
    }
    await renderCreate(panel, ctx);
  }
}

function lineSummaryRowHtml(line: DraftLine, index: number, gstReg: boolean): string {
  const total = draftLineAmount(line);
  const totalText = total == null ? "—" : formatMoney(total);
  const desc = esc(line.description || "Untitled");
  const gstBadge = gstReg
    ? `<span class="line-summary-gst">${line.gst_applicable ? "GST applicable" : "GST-free"}</span>`
    : "";
  return `<article class="line-summary" data-id="${esc(line.id)}" data-index="${index}">
    <button type="button" class="line-drag-handle" aria-label="Reorder line" title="Drag to reorder">⋮⋮</button>
    <button type="button" class="line-summary-main line-summary-main-compact">
      <span class="line-summary-desc">${desc}</span>
      ${gstBadge}
      <span class="line-summary-total">${totalText}</span>
    </button>
    <button type="button" class="btn icon-btn remove-line" aria-label="Remove line" title="Remove line">×</button>
  </article>`;
}

function wireLineSummaryList(panel: HTMLElement, gstReg: boolean, onChange: () => void) {
  panel.querySelectorAll("#line-items .line-summary").forEach((el) => {
    const row = el as HTMLElement;
    const id = row.dataset.id || "";
    row.querySelector(".line-summary-main")?.addEventListener("click", async () => {
      const line = draftLines.find((l) => l.id === id);
      if (!line) return;
      const saved = await openLineItemSheet({ gstReg, initial: line });
      if (!saved) return;
      const idx = draftLines.findIndex((l) => l.id === id);
      if (idx >= 0) draftLines[idx] = saved;
      onChange();
    });
    row.querySelector(".remove-line")?.addEventListener("click", (e) => {
      e.stopPropagation();
      draftLines = draftLines.filter((l) => l.id !== id);
      onChange();
    });
  });
  wireLineReorder(panel, onChange);
}

function wireLineReorder(panel: HTMLElement, onChange: () => void) {
  const stack = panel.querySelector("#line-items") as HTMLElement | null;
  if (!stack) return;

  stack.querySelectorAll(".line-drag-handle").forEach((handleEl) => {
    const handle = handleEl as HTMLElement;
    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const row = handle.closest(".line-summary") as HTMLElement | null;
      if (!row) return;
      e.preventDefault();
      e.stopPropagation();

      let currentIndex = Number(row.dataset.index);
      let lastSwapY = e.clientY;
      handle.setPointerCapture(e.pointerId);
      row.classList.add("line-summary-dragging");

      const onMove = (ev: PointerEvent) => {
        if (ev.pointerId !== e.pointerId) return;
        const dy = ev.clientY - lastSwapY;
        const rows = [...stack.querySelectorAll(".line-summary")] as HTMLElement[];
        if (dy > 28 && currentIndex < rows.length - 1) {
          stack.insertBefore(rows[currentIndex + 1], rows[currentIndex]);
          const tmp = draftLines[currentIndex];
          draftLines[currentIndex] = draftLines[currentIndex + 1];
          draftLines[currentIndex + 1] = tmp;
          currentIndex += 1;
          lastSwapY = ev.clientY;
          renumberSummaryDom(stack);
        } else if (dy < -28 && currentIndex > 0) {
          stack.insertBefore(rows[currentIndex], rows[currentIndex - 1]);
          const tmp = draftLines[currentIndex];
          draftLines[currentIndex] = draftLines[currentIndex - 1];
          draftLines[currentIndex - 1] = tmp;
          currentIndex -= 1;
          lastSwapY = ev.clientY;
          renumberSummaryDom(stack);
        }
      };

      const onUp = (ev: PointerEvent) => {
        if (ev.pointerId !== e.pointerId) return;
        try {
          handle.releasePointerCapture(ev.pointerId);
        } catch {
          /* ignore */
        }
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        row.classList.remove("line-summary-dragging");
        onChange();
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  });
}

function renumberSummaryDom(stack: HTMLElement) {
  stack.querySelectorAll(".line-summary").forEach((el, i) => {
    (el as HTMLElement).dataset.index = String(i);
  });
}

async function openLineItemSheet(opts: {
  gstReg: boolean;
  initial?: DraftLine;
}): Promise<DraftLine | null> {
  const editing = Boolean(opts.initial);
  const init = opts.initial || {
    id: newDraftLineId(),
    description: "",
    qty: "1",
    amount: "",
    gst_applicable: true,
  };
  const unitLabel = opts.gstReg ? "Unit amount ex GST" : "Unit amount";
  const gstBlock = opts.gstReg
    ? `<label class="gst-line-toggle sheet-gst-toggle" title="GST applicable when on; GST-free when off">
        <input type="checkbox" name="item_gst_applicable" id="sheet-gst-applicable" ${
          init.gst_applicable ? "checked" : ""
        }>
        <span class="gst-toggle-text">${init.gst_applicable ? "GST applicable" : "GST-free"}</span>
        <span class="gst-toggle-switch" aria-hidden="true"></span>
      </label>`
    : "";

  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "sheet-overlay";
    overlay.innerHTML = `
      <div class="sheet sheet-tall" role="dialog" aria-modal="true">
        <div class="sheet-handle" aria-hidden="true"></div>
        <div class="sheet-header">
          <h3 class="sheet-title">${editing ? "Edit line" : "Add line"}</h3>
          ${gstBlock}
        </div>
        <form id="line-item-sheet-form" class="sheet-body" novalidate>
          <div class="field"><label for="sheet-item-desc">Description</label>
            <input name="item_description" id="sheet-item-desc" value="${esc(init.description)}" required></div>
          <div class="line-item-amounts">
            <div class="field"><label for="sheet-item-qty">Qty</label>
              <input name="item_qty" id="sheet-item-qty" inputmode="decimal" value="${esc(init.qty || "1")}"></div>
            <div class="field"><label for="sheet-item-amount">${unitLabel}</label>
              <input name="item_amount" id="sheet-item-amount" inputmode="decimal" value="${esc(init.amount)}" required></div>
            <div class="field"><label>Line total</label>
              <div class="line-item-subtotal" id="sheet-line-total" aria-live="polite">—</div></div>
          </div>
          <p class="error-text" id="line-sheet-error" hidden></p>
        </form>
        <div class="sheet-actions">
          <button type="button" class="btn secondary" data-act="cancel">Cancel</button>
          <button type="button" class="btn primary" data-act="save">Save</button>
        </div>
      </div>`;
    const sheet = overlay.querySelector(".sheet") as HTMLElement;
    const form = overlay.querySelector("#line-item-sheet-form") as HTMLFormElement;
    const close = (v: DraftLine | null) => {
      overlay.remove();
      resolve(v);
    };
    wireSheetGrabDismiss(overlay, sheet, () => close(null));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });
    overlay.querySelector('[data-act="cancel"]')?.addEventListener("click", () => close(null));

    const syncSheetTotal = () => {
      const qty = (form.querySelector('[name="item_qty"]') as HTMLInputElement)?.value;
      const amount = (form.querySelector('[name="item_amount"]') as HTMLInputElement)?.value;
      const total = draftLineAmount({
        id: init.id,
        description: "",
        qty: qty || "1",
        amount: amount || "",
        gst_applicable: true,
      });
      const el = overlay.querySelector("#sheet-line-total");
      if (el) el.textContent = total == null ? "—" : formatMoney(total);
    };
    form.addEventListener("input", syncSheetTotal);
    syncSheetTotal();

    const qtyInput = form.querySelector("#sheet-item-qty") as HTMLInputElement | null;
    qtyInput?.addEventListener("focus", () => {
      if (String(qtyInput.value || "").trim() === "1") qtyInput.value = "";
    });
    qtyInput?.addEventListener("blur", () => {
      if (!String(qtyInput.value || "").trim()) {
        qtyInput.value = "1";
        syncSheetTotal();
      }
    });

    const gstInput = overlay.querySelector("#sheet-gst-applicable") as HTMLInputElement | null;
    const gstText = overlay.querySelector(".gst-toggle-text");
    gstInput?.addEventListener("change", () => {
      if (gstText) gstText.textContent = gstInput.checked ? "GST applicable" : "GST-free";
    });
    overlay.querySelector(".sheet-gst-toggle")?.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
    });

    overlay.querySelector('[data-act="save"]')?.addEventListener("click", () => {
      const err = overlay.querySelector("#line-sheet-error") as HTMLElement;
      err.hidden = true;
      try {
        const fd = new FormData(form);
        const description = String(fd.get("item_description") || "").trim();
        const qty = String(fd.get("item_qty") || "1").trim() || "1";
        const amount = String(fd.get("item_amount") || "").trim();
        if (!description) throw new Error("Add a description.");
        if (!amount) throw new Error("Enter a unit amount.");
        parseLineItems(
          [
            {
              description,
              qty,
              amount,
              gst_free: opts.gstReg && gstInput ? !gstInput.checked : false,
            },
          ],
          opts.gstReg
        );
        close({
          id: init.id,
          description,
          qty,
          amount,
          gst_applicable: opts.gstReg ? Boolean(gstInput?.checked ?? true) : true,
        });
      } catch (ex) {
        err.textContent = ex instanceof Error ? ex.message : "Invalid line.";
        err.hidden = false;
      }
    });

    document.body.appendChild(overlay);
  });
}

function totalsHtml(
  gstReg: boolean,
  taxable: number,
  gstFree: number,
  gst: number,
  total: number
) {
  if (!gstReg) {
    return `<div class="preview-row"><span>Total</span><strong>${formatMoney(total)}</strong></div>`;
  }
  let html = "";
  if (taxable > 0 && gstFree > 0) {
    html += `<div class="preview-row"><span>Taxable ex GST</span><span>${formatMoney(taxable)}</span></div>`;
    html += `<div class="preview-row"><span>GST-free ex GST</span><span>${formatMoney(gstFree)}</span></div>`;
  }
  html += `<div class="preview-row"><span>GST (10%)</span><span>${formatMoney(gst)}</span></div>`;
  html += `<div class="preview-row"><span>Total inc GST</span><strong>${formatMoney(total)}</strong></div>`;
  return html;
}

async function renderSuccess(panel: HTMLElement, ctx: AppContext): Promise<void> {
  revokeSuccessPdfUrl();
  const key = String(router.params.name || "").trim();
  const [invoices, customers] = await Promise.all([
    cache.getInvoices(),
    cache.getCustomers(),
  ]);
  const inv = invoices[key];
  if (!inv) {
    router.navigate("invoices");
    return renderInvoices(panel, ctx);
  }
  const n = Number(inv.invoice_number);
  const customer = customers[String(inv.customer_name)] || {};
  const sendEmail = String(inv.customer_email || customer.email || "").trim();
  const hasEmail = Boolean(sendEmail);
  const canSend = ["not_sent", "send_failed"].includes(String(inv.status || "not_sent"));

  panel.innerHTML = `
    <section class="panel success-panel">
      <div class="panel-header">
        <div>
          <h2>Invoice saved</h2>
          <p class="hint">#${formatInvoiceNumber(n)} · ${formatMoney(Number(inv.total_inc_gst || 0))}</p>
        </div>
        <button type="button" class="btn small ghost" id="success-edit">Edit</button>
      </div>
      <div class="pdf-embed-wrap" id="pdf-embed-wrap">
        <p class="hint pdf-embed-loading" id="pdf-embed-loading">Preparing PDF…</p>
        <iframe class="pdf-embed" id="pdf-embed" title="Invoice PDF" hidden></iframe>
      </div>
      <p class="error-text" id="pdf-embed-error" hidden></p>
      <div class="btn-row stacked">
        <button type="button" class="btn secondary" id="success-download" disabled>Download PDF</button>
        <button type="button" class="btn primary" id="success-send" ${!hasEmail || !canSend ? "disabled" : ""}>Send to customer</button>
        ${!hasEmail ? `<p class="hint">Add an email to send this invoice automatically.</p>` : ""}
        <p class="hint">Ask them to use invoice number <strong>${formatInvoiceNumber(n)}</strong> as the bank transfer reference.</p>
        <button type="button" class="btn ghost" id="success-done">Done</button>
      </div>
    </section>`;

  let pdfFilename = `Invoice_${formatInvoiceNumber(n)}.pdf`;

  const leaveSuccess = () => {
    revokeSuccessPdfUrl();
    router.navigate("invoices");
  };

  panel.querySelector("#success-edit")?.addEventListener("click", () => {
    revokeSuccessPdfUrl();
    loadInvoiceIntoCreateDraft(inv);
    router.navigate("invoices", "create");
  });

  panel.querySelector("#success-done")?.addEventListener("click", leaveSuccess);

  panel.querySelector("#success-download")?.addEventListener("click", () => {
    if (!successPdfUrl) {
      showToast("PDF not ready yet.", "error");
      return;
    }
    downloadPdf(successPdfUrl, pdfFilename);
  });

  panel.querySelector("#success-send")?.addEventListener("click", async () => {
    try {
      showToast("Sending…", "success");
      const sendResult = await queueEmailSend(key);
      trackEvent("send_invoice");
      await flushQueue(ctx.onSyncStatus);
      if (sendResult.finalStatus === "send_failed") {
        showToast("Send failed. Check the customer email and try again.", "error");
        return;
      }
      if (sendResult.finalStatus === "sent") {
        showToast("Invoice sent.", "success");
        leaveSuccess();
        return;
      }
      revokeSuccessPdfUrl();
      router.navigate("invoices");
      void reconcileEmailSendStatus(key).then(async (status) => {
        if (status === "sent") showToast("Invoice sent.", "success");
        else if (status === "send_failed") {
          showToast("Send failed. Check the customer email and try again.", "error");
        }
        await refreshInvoicesListIfVisible(ctx);
      });
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Send failed.", "error");
    }
  });

  const loading = panel.querySelector("#pdf-embed-loading") as HTMLElement | null;
  const iframe = panel.querySelector("#pdf-embed") as HTMLIFrameElement | null;
  const errEl = panel.querySelector("#pdf-embed-error") as HTMLElement | null;
  const downloadBtn = panel.querySelector("#success-download") as HTMLButtonElement | null;

  try {
    const pdf = await fetchPdfBlob(key);
    revokeSuccessPdfUrl();
    successPdfUrl = pdf.url;
    pdfFilename = pdf.filename;
    if (iframe) {
      iframe.src = pdf.url;
      iframe.hidden = false;
    }
    if (loading) loading.hidden = true;
    if (downloadBtn) downloadBtn.disabled = false;
  } catch (ex) {
    if (loading) loading.hidden = true;
    if (errEl) {
      errEl.textContent = ex instanceof Error ? ex.message : "Could not load PDF.";
      errEl.hidden = false;
    }
  }
}
