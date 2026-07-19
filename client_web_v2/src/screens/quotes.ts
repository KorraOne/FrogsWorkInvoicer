import { fetchQuotePdf } from "../api/mobile";
import { formSectionHtml } from "../components/forms";
import { confirmSheet, emptyStateHtml, openSheet, showToast, wireSheetGrabDismiss } from "../components/ui";
import { trackEvent } from "../lib/analytics";
import { cache } from "../data/idb";
import {
  convertQuoteToInvoice,
  flushQueue,
  newInvoiceId,
  newQuoteId,
  pullBootstrap,
  queueQuoteEmail,
  reconcileQuoteEmailSendStatus,
  saveQuotePackage,
  softDeleteQuote,
  updateQuoteStatus,
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
import { quoteStorageKey, suggestedQuoteNumber } from "../domain/quoteIdentity";
import {
  openInvoicesFiltered,
  registerQuoteListFilter,
} from "../domain/crossDocNav";
import {
  countActiveQuoteFilters,
  daysSinceSent,
  docKindLabel,
  filterQuotes,
  quotesByStatus,
  statusLabel,
  type QuoteFilters,
} from "../domain/quotesGroup";
import { esc } from "../lib/escape";
import { filesToWorkPhotos } from "../lib/images";
import { router } from "../router";
import type { AppContext } from "../types";

let filterState: QuoteFilters = {};
let filtersOpen = false;
let draft: Record<string, unknown> | null = null;
let draftPhotos: string[] = [];
/** One-off customers for the current create flow. */
let ephemeralCustomers: Record<string, Record<string, unknown>> = {};
let successPdfUrl: string | null = null;

type DraftLine = {
  id: string;
  description: string;
  qty: string;
  amount: string;
  gst_applicable: boolean;
};

let draftLines: DraftLine[] = [];

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

function captureCreateFormState(panel: HTMLElement) {
  const form = panel.querySelector("#create-quote-form") as HTMLFormElement | null;
  if (!form) return;
  const fd = new FormData(form);
  draft = {
    ...(draft || {}),
    customer_name: String(fd.get("customer") || draft?.customer_name || "").trim(),
    business_name: String(fd.get("business") || draft?.business_name || "").trim(),
    quote_number: String(fd.get("quote_number") || draft?.quote_number || "").trim(),
    quote_date: String(fd.get("quote_date") || draft?.quote_date || "").trim(),
    doc_kind: String(fd.get("doc_kind") || draft?.doc_kind || "quote").trim(),
    comment: String(fd.get("comment") || "").trim(),
  };
}

function loadQuoteIntoCreateDraft(quote: Record<string, unknown>) {
  draft = { ...quote };
  draftPhotos = [...((quote.work_photos_b64 as string[]) || [])];
  const items = (quote.line_items as Array<Record<string, unknown>> | undefined) || [];
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
  quoteId: string
): Promise<{ blob: Blob; filename: string; url: string }> {
  const key = String(quoteId || "").trim();
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
      const data = await fetchQuotePdf(key);
      const binary = atob(data.content_b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: "application/pdf" });
      const filename = String(data.filename || `Quote_${key}.pdf`).trim() || "quote.pdf";
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
  a.download = filename || "quote.pdf";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function openPdf(quoteId: string) {
  const { url, filename } = await fetchPdfBlob(quoteId);
  try {
    downloadPdf(url, filename);
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}

function resolveCustomerProfile(
  name: string,
  customers: Record<string, Record<string, unknown>>
): Record<string, unknown> {
  return customers[name] || ephemeralCustomers[name] || {};
}

function snapshotCustomerOntoDoc(
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

export function openQuotesFiltered(q: string) {
  filterState = { q: String(q || "").trim() };
  filtersOpen = true;
  router.navigate("quotes");
}

registerQuoteListFilter((q) => {
  filterState = { q };
  filtersOpen = true;
});

function customerFilterNames(
  customers: Record<string, Record<string, unknown>>,
  quotes: Record<string, Record<string, unknown>>
): string[] {
  const names = new Set(Object.keys(customers));
  for (const quote of Object.values(quotes)) {
    if (quote.deleted_at) continue;
    const n = String(quote.customer_name || "").trim();
    if (n) names.add(n);
  }
  return [...names].sort();
}

function searchQFromNumber(raw: unknown): string {
  const n = parseInt(String(raw ?? ""), 10);
  return Number.isFinite(n) && n > 0 ? String(n) : String(raw || "").trim();
}

function convertedInvoiceMeta(
  quote: Record<string, unknown>,
  invoices: Record<string, Record<string, unknown>>
): string {
  const id = String(quote.converted_invoice_id || "").trim();
  let num = quote.converted_invoice_number;
  let exists = false;
  if (id && invoices[id] && !invoices[id].deleted_at) {
    exists = true;
    if (num == null || num === "") num = invoices[id].invoice_number;
  } else if (num != null && num !== "") {
    const target = Number(num);
    exists = Object.values(invoices).some(
      (inv) => !inv.deleted_at && Number(inv.invoice_number) === target
    );
  } else if (id) {
    return `<div class="meta">Converted to invoice (removed)</div>`;
  } else {
    return "";
  }
  if (num == null || num === "") return "";
  const display = formatInvoiceNumber(num as string | number);
  const q = searchQFromNumber(num);
  if (exists && q) {
    return `<div class="meta"><button type="button" class="meta-link" data-action="goto-invoice" data-q="${esc(q)}">Converted to invoice #${display} ›</button></div>`;
  }
  return `<div class="meta">Converted to invoice #${display}</div>`;
}

export async function renderQuotes(panel: HTMLElement, ctx: AppContext): Promise<void> {
  if (router.sub === "create") return renderCreate(panel, ctx);
  if (router.sub === "success") return renderSuccess(panel, ctx);

  const [quotes, customers, businesses, invoices] = await Promise.all([
    cache.getQuotes(),
    cache.getCustomers(),
    cache.getBusinesses(),
    cache.getInvoices(),
  ]);

  const filtered = filterQuotes(quotes, filterState);
  const filteredMap = Object.fromEntries(
    filtered.map((q) => [quoteStorageKey(q), q])
  );
  const { groups } = quotesByStatus(filteredMap);
  const multiBiz = Object.keys(businesses).length > 1;
  const customerNames = customerFilterNames(customers, quotes);
  const businessNames = Object.keys(businesses).sort();
  const activeFilterCount = countActiveQuoteFilters(filterState);
  const totalCount =
    groups.not_sent.length + groups.sent.length + groups.closed.length + groups.converted.length;

  panel.innerHTML = `
    <div class="panel-header">
      <h2>Quotes</h2>
      <button type="button" class="btn small primary" id="new-quote">Create</button>
    </div>
    <button type="button" class="btn small secondary filters-toggle" id="toggle-filters">
      Filters${activeFilterCount ? ` · ${activeFilterCount} active` : ""} ▾
    </button>
    <form id="quote-filters" class="panel filters-panel" ${filtersOpen ? "" : "hidden"}>
      <div class="field"><label>Search</label><input name="q" value="${esc(filterState.q || "")}" placeholder="Number, customer, description"></div>
      <div class="field-row">
        <div class="field"><label>Status</label>
          <select name="status">
            <option value="">All</option>
            <option value="not_sent" ${filterState.status === "not_sent" ? "selected" : ""}>Not sent</option>
            <option value="sent" ${filterState.status === "sent" ? "selected" : ""}>Sent</option>
            <option value="closed" ${filterState.status === "closed" ? "selected" : ""}>Closed</option>
            <option value="converted" ${filterState.status === "converted" ? "selected" : ""}>Converted</option>
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
        ? `${renderGroup("Not sent", "not_sent", groups.not_sent, multiBiz, invoices, activeFilterCount > 0)}
           ${renderGroup("Sent", "sent", groups.sent, multiBiz, invoices, activeFilterCount > 0)}
           ${renderGroup("Closed", "closed", groups.closed, multiBiz, invoices, activeFilterCount > 0)}
           ${renderGroup("Converted", "converted", groups.converted, multiBiz, invoices, activeFilterCount > 0)}`
        : activeFilterCount
          ? `<div class="panel"><p class="hint">No matching quotes.</p>
             <button type="button" class="btn small ghost" id="clear-filters-empty">Clear filters</button></div>`
          : emptyStateHtml(
              "No quotes yet",
              "Create a quote or price estimate for a customer.",
              "empty-create",
              "Create quote"
            )
    }`;

  panel.querySelector("#new-quote")?.addEventListener("click", () =>
    router.navigate("quotes", "create")
  );
  panel.querySelector("#empty-create")?.addEventListener("click", () =>
    router.navigate("quotes", "create")
  );
  panel.querySelector("#toggle-filters")?.addEventListener("click", () => {
    filtersOpen = !filtersOpen;
    renderQuotes(panel, ctx);
  });
  panel.querySelector("#quote-filters")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    filterState = Object.fromEntries(fd.entries()) as QuoteFilters;
    renderQuotes(panel, ctx);
  });
  const clearFilters = () => {
    filterState = {};
    renderQuotes(panel, ctx);
  };
  panel.querySelector("#clear-filters")?.addEventListener("click", clearFilters);
  panel.querySelector("#clear-filters-empty")?.addEventListener("click", clearFilters);
  wireListActions(panel, ctx, customers, businesses);
}

function renderGroup(
  title: string,
  key: string,
  items: Record<string, unknown>[],
  multiBiz: boolean,
  invoices: Record<string, Record<string, unknown>>,
  forceOpen = false
) {
  if (!items.length) {
    return `<details class="invoice-group"><summary>${title} (0)</summary><p class="hint">None</p></details>`;
  }
  const open = forceOpen || key === "not_sent" || key === "sent";
  return `<details class="invoice-group" ${open ? "open" : ""}>
    <summary>${title} (${items.length})</summary>
    ${items.map((q) => quoteCard(q, multiBiz, invoices)).join("")}
  </details>`;
}

function quoteCard(
  quote: Record<string, unknown>,
  multiBiz: boolean,
  invoices: Record<string, Record<string, unknown>>
) {
  const n = Number(quote.quote_number);
  const id = esc(quoteStorageKey(quote));
  const status = String(quote.status || "not_sent");
  const kind = docKindLabel(String(quote.doc_kind || "quote"));
  const canSend = ["not_sent", "send_failed"].includes(status);
  const days = status === "sent" ? daysSinceSent(quote) : null;
  const daysLabel =
    days == null
      ? ""
      : days === 0
        ? "Sent today"
        : days === 1
          ? "Sent 1 day ago"
          : `Sent ${days} days ago`;
  return `<article class="card" data-quote="${id}">
    <div class="card-top">
      <strong>${esc(kind)} #${formatInvoiceNumber(n)}</strong>
      <span class="badge badge-${status}">${statusLabel(status)}</span>
    </div>
    <div class="meta">${formatInvoiceDate(String(quote.quote_date || ""))} · ${esc(String(quote.customer_name || ""))}</div>
    ${multiBiz && quote.business_name ? `<div class="meta">From: ${esc(String(quote.business_name))}</div>` : ""}
    <div class="meta">${formatMoney(Number(quote.total_inc_gst || 0))} · ${esc(lineItemsSummary(quote))}</div>
    ${daysLabel ? `<div class="meta">${esc(daysLabel)}</div>` : ""}
    ${status === "converted" ? convertedInvoiceMeta(quote, invoices) : ""}
    <div class="actions">
      ${canSend ? `<button class="btn small primary" data-action="send" data-id="${id}">Send</button>` : ""}
      ${
        status === "sent"
          ? `<button class="btn small primary" data-action="convert" data-id="${id}">Create invoice</button>
             <button class="btn small secondary" data-action="close" data-id="${id}">Close</button>`
          : ""
      }
      <button class="btn small secondary" data-action="pdf" data-id="${id}">View PDF</button>
      <button class="btn small ghost" data-action="more" data-id="${id}" data-n="${n}" aria-label="More actions">···</button>
    </div>
  </article>`;
}

async function refreshQuotesListIfVisible(ctx: AppContext) {
  if (router.tab !== "quotes" || router.sub) return;
  const listPanel = document.getElementById("tab-quotes") as HTMLElement | null;
  if (!listPanel) return;
  await renderQuotes(listPanel, ctx);
}

function wireListActions(
  panel: HTMLElement,
  ctx: AppContext,
  customers: Record<string, Record<string, unknown>>,
  businesses: Record<string, Record<string, unknown>>
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
          const sendResult = await queueQuoteEmail(id);
          trackEvent("send_quote");
          await flushQueue(ctx.onSyncStatus);
          if (sendResult.finalStatus === "sent") {
            showToast("Quote sent.", "success");
          } else if (sendResult.finalStatus === "send_failed") {
            showToast("Send failed. Check the customer email and try again.", "error");
          } else {
            void reconcileQuoteEmailSendStatus(id).then(async (status) => {
              if (status === "sent") showToast("Quote sent.", "success");
              else if (status === "send_failed") {
                showToast("Send failed. Check the customer email and try again.", "error");
              }
              await refreshQuotesListIfVisible(ctx);
            });
          }
        } else if (action === "close") {
          await updateQuoteStatus(id, "closed");
          await flushQueue(ctx.onSyncStatus);
          showToast("Quote closed.", "success");
        } else if (action === "convert") {
          await convertQuoteAndOpenInvoice(panel, ctx, id, businesses);
          return;
        } else if (action === "pdf") {
          await openPdf(id);
        } else if (action === "goto-invoice") {
          const q = String(el.dataset.q || "").trim();
          if (q) openInvoicesFiltered(q);
          return;
        } else if (action === "more") {
          await handleMoreActions(panel, ctx, id, n, customers, businesses);
          return;
        }
        await renderQuotes(panel, ctx);
      } catch (ex) {
        showToast(ex instanceof Error ? ex.message : "Action failed.", "error");
      }
    });
  });
}

async function convertQuoteAndOpenInvoice(
  _panel: HTMLElement,
  ctx: AppContext,
  quoteId: string,
  businesses: Record<string, Record<string, unknown>>
) {
  const quotes = await cache.getQuotes();
  const quote = quotes[quoteId];
  if (!quote) throw new Error("Quote not found.");
  const invoices = await cache.getInvoices();
  const businessName = String(quote.business_name || "").trim();
  const biz = businesses[businessName] || {};
  const invoiceNumber = suggestedInvoiceNumber(businessName, biz, invoices);
  const invoiceId = newInvoiceId();
  const invoicePayload: Record<string, unknown> = {
    invoice_id: invoiceId,
    invoice_number: invoiceNumber,
    invoice_date: todayIso(),
    customer_name: quote.customer_name,
    customer_email: quote.customer_email,
    customer_abn: quote.customer_abn,
    address_line1: quote.address_line1,
    address_line2: quote.address_line2,
    suburb: quote.suburb,
    state: quote.state,
    postcode: quote.postcode,
    business_name: businessName,
    line_items: quote.line_items,
    description: quote.description,
    amount_ex_gst: quote.amount_ex_gst,
    gst_amount: quote.gst_amount,
    total_inc_gst: quote.total_inc_gst,
    taxable_ex_gst: quote.taxable_ex_gst,
    gst_free_ex_gst: quote.gst_free_ex_gst,
    gst_registered: quote.gst_registered,
    comment: quote.comment,
    work_photos_b64: quote.work_photos_b64 || [],
    status: "not_sent",
    pdf_status: "pending",
    source_quote_id: quoteId,
    source_quote_number: quote.quote_number,
  };
  const savedInvoiceId = await convertQuoteToInvoice(quoteId, invoicePayload, {
    preparePdf: true,
    businessName,
    usedInvoiceNumber: invoiceNumber,
  });
  await flushQueue(ctx.onSyncStatus);
  showToast("Invoice created from quote.", "success");
  router.navigate("invoices", "success", { name: savedInvoiceId });
}

async function handleMoreActions(
  panel: HTMLElement,
  ctx: AppContext,
  quoteId: string,
  n: number,
  _customers: Record<string, Record<string, unknown>>,
  businesses: Record<string, Record<string, unknown>>
) {
  const quotes = await cache.getQuotes();
  const quote = quotes[quoteId];
  const status = String(quote?.status || "not_sent");
  const actions = [
    ...(status === "sent"
      ? [
          { id: "convert", label: "Create invoice", className: "btn primary" },
          { id: "closed", label: "Close", className: "btn secondary" },
        ]
      : []),
    { id: "edit", label: "Edit", className: "btn secondary" },
    { id: "delete", label: "Remove", className: "btn danger" },
    { id: "cancel", label: "Cancel", className: "btn ghost" },
  ];
  const choice = await openSheet({
    title: `#${formatInvoiceNumber(n)}`,
    bodyHtml: `<p class="hint">Edit, convert, or remove this quote.</p>`,
    actions,
  });
  if (!choice || choice === "cancel") return;
  try {
    if (choice === "delete") {
      const ok = await confirmSheet(`Remove quote #${formatInvoiceNumber(n)}?`, "Remove");
      if (!ok) return;
      await softDeleteQuote(quoteId);
      await flushQueue(ctx.onSyncStatus);
      showToast("Quote removed.", "success");
      await renderQuotes(panel, ctx);
    } else if (choice === "closed") {
      await updateQuoteStatus(quoteId, "closed");
      await flushQueue(ctx.onSyncStatus);
      showToast("Quote closed.", "success");
      await renderQuotes(panel, ctx);
    } else if (choice === "convert") {
      await convertQuoteAndOpenInvoice(panel, ctx, quoteId, businesses);
    } else if (choice === "edit") {
      if (quote) loadQuoteIntoCreateDraft(quote);
      router.navigate("quotes", "create");
    }
  } catch (ex) {
    showToast(ex instanceof Error ? ex.message : "Action failed.", "error");
  }
}

async function renderCreate(panel: HTMLElement, ctx: AppContext) {
  const [businesses, customers, quotes, settings] = await Promise.all([
    cache.getBusinesses(),
    cache.getCustomers(),
    cache.getQuotes(),
    cache.getSettings(),
  ]);
  const bizNames = Object.keys(businesses);
  const defaultBiz =
    settings.default_business && businesses[String(settings.default_business)]
      ? String(settings.default_business)
      : bizNames[0] || "";
  const restoring = Boolean(draft?.customer_name || draft?.quote_number);
  const selectedBiz =
    restoring && draft?.business_name && businesses[String(draft.business_name)]
      ? String(draft.business_name)
      : defaultBiz;
  const biz = businesses[selectedBiz] || {};
  const gstReg = anyBusinessGstRegistered(businesses);
  const suggested = suggestedQuoteNumber(selectedBiz, biz, quotes);
  const selectedCustomer = restoring ? String(draft?.customer_name || "") : "";
  const quoteNumberValue = restoring
    ? String(draft?.quote_number ?? suggested)
    : String(suggested);
  const quoteDateValue = restoring
    ? String(draft?.quote_date || todayIso())
    : todayIso();
  const docKind = restoring
    ? String(draft?.doc_kind || "quote").toLowerCase() === "estimate"
      ? "estimate"
      : "quote"
    : "quote";

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
  const numDisplay = formatInvoiceNumber(Number(quoteNumberValue) || quoteNumberValue);
  const dateDisplay = formatInvoiceDate(quoteDateValue);

  const photoThumbs = draftPhotos
    .map(
      (src, i) =>
        `<div class="photo-thumb"><img src="${src}" alt="Work photo ${i + 1}"><button type="button" class="btn small ghost remove-photo" data-i="${i}">×</button></div>`
    )
    .join("");

  const detailsBody = `
      <div class="field"><label>Type</label>
        <select name="doc_kind">
          <option value="quote" ${docKind === "quote" ? "selected" : ""}>Quote</option>
          <option value="estimate" ${docKind === "estimate" ? "selected" : ""}>Price estimate</option>
        </select>
      </div>
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
          <button type="button" class="inv-num-btn" id="quote-num-toggle" aria-expanded="false">
            <strong id="quote-num-label">#${esc(String(numDisplay))}</strong>
            <span class="inv-num-hint">Change</span>
          </button>
        </div>
        <div class="inv-meta-date">
          <span class="inv-date-label">Date</span>
          <span class="inv-date-value">${esc(dateDisplay)}</span>
          <input type="hidden" name="quote_date" value="${esc(quoteDateValue)}">
        </div>
      </div>
      <div class="inv-num-edit" id="quote-num-edit" hidden>
        <div class="field"><label for="quote_number_input">Number</label>
          <input name="quote_number" id="quote_number_input" value="${esc(quoteNumberValue)}" inputmode="numeric"></div>
      </div>
      <input type="hidden" name="quote_number_default" value="${esc(String(suggested))}">`;

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

  const notesBody = `<div class="field"><label>Notes (optional)</label><textarea name="comment" rows="2" placeholder="Shown on the quote">${esc(String(draft?.comment || ""))}</textarea></div>`;

  const photosBody = `
      <p class="hint">Optional, max 6</p>
      <input type="file" id="work-photos" class="sr-only" accept="image/*" multiple>
      <button type="button" class="btn small secondary" id="add-photos-btn">Add photos</button>
      <div class="photo-grid" id="photo-grid">${photoThumbs}</div>
      <p class="hint">${draftPhotos.length}/6 photos</p>`;

  panel.innerHTML = `
    <form id="create-quote-form" class="panel" novalidate>
      <div class="panel-header">
        <h2>Create quote</h2>
        <button type="button" class="btn small ghost" id="cancel-create">Cancel</button>
      </div>
      ${formSectionHtml("Details", detailsBody)}
      ${formSectionHtml("Customer", customerBody)}
      ${formSectionHtml("Line items", linesBody)}
      ${formSectionHtml("Notes", notesBody)}
      ${formSectionHtml("Work photos", photosBody)}
      <div class="preview-section totals-panel" id="live-totals"></div>
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-quote">Save</button>
      </div>
    </form>`;

  const form = panel.querySelector("#create-quote-form") as HTMLFormElement;

  const syncNumLabel = () => {
    const input = panel.querySelector("#quote_number_input") as HTMLInputElement | null;
    const label = panel.querySelector("#quote-num-label");
    if (!input || !label) return;
    try {
      label.textContent = `#${formatInvoiceNumber(parseInvoiceNumberInput(input.value))}`;
    } catch {
      /* keep */
    }
  };

  const setNumEditOpen = (open: boolean) => {
    const edit = panel.querySelector("#quote-num-edit") as HTMLElement | null;
    const btn = panel.querySelector("#quote-num-toggle") as HTMLButtonElement | null;
    const hint = panel.querySelector(".inv-num-hint");
    if (edit) edit.hidden = !open;
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (hint) hint.textContent = open ? "Done" : "Change";
    if (!open) {
      const input = panel.querySelector("#quote_number_input") as HTMLInputElement | null;
      const def = (panel.querySelector('[name="quote_number_default"]') as HTMLInputElement)
        ?.value;
      if (input && def && !String(input.value || "").trim()) input.value = def;
      syncNumLabel();
    }
  };

  panel.querySelector("#quote-num-toggle")?.addEventListener("click", () => {
    const edit = panel.querySelector("#quote-num-edit") as HTMLElement | null;
    setNumEditOpen(Boolean(edit?.hidden));
  });
  panel.querySelector("#quote_number_input")?.addEventListener("input", syncNumLabel);

  form.querySelector('[name="business"]')?.addEventListener("change", () => {
    const bizSelect = form.querySelector('[name="business"]') as HTMLSelectElement | null;
    const bizName = bizSelect?.value || selectedBiz;
    const nextSuggested = suggestedQuoteNumber(bizName, businesses[bizName] || {}, quotes);
    const defInput = form.querySelector('[name="quote_number_default"]') as HTMLInputElement | null;
    const numInput = form.querySelector("#quote_number_input") as HTMLInputElement | null;
    if (defInput) defInput.value = String(nextSuggested);
    if (numInput && String(numInput.value) === String(quoteNumberValue)) {
      numInput.value = String(nextSuggested);
      syncNumLabel();
    }
  });

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
    router.navigate("quotes");
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

  panel.querySelector("#save-quote")?.addEventListener("click", async () => {
    const err = panel.querySelector("#form-error") as HTMLElement;
    err.hidden = true;
    const saveBtn = panel.querySelector("#save-quote") as HTMLButtonElement | null;
    if (saveBtn) saveBtn.disabled = true;
    try {
      const fd = new FormData(form);
      const businessName = String(fd.get("business") || selectedBiz);
      const gstRegistered = gstReg;
      const parsed = parseLineItems(readDraftLineRows(gstRegistered), gstRegistered);
      const customerName = String(fd.get("customer") || "").trim();
      if (!customerName) throw new Error("Select a customer.");
      const custProfile = resolveCustomerProfile(customerName, customers);
      const quoteNumber = parseInvoiceNumberInput(String(fd.get("quote_number")));
      const kind =
        String(fd.get("doc_kind") || "quote").toLowerCase() === "estimate" ? "estimate" : "quote";
      const quoteId = String(draft?.quote_id || "").trim() || newQuoteId();
      const toSave: Record<string, unknown> = {
        quote_id: quoteId,
        quote_number: quoteNumber,
        quote_date: String(fd.get("quote_date") || todayIso()),
        doc_kind: kind,
        ...snapshotCustomerOntoDoc(customerName, custProfile),
        business_name: businessName,
        line_items: parsed.items,
        description: parsed.items.map((i) => i.description).join("; "),
        amount_ex_gst: moneyStr(parsed.subtotal),
        gst_amount: moneyStr(parsed.gstAmount),
        total_inc_gst: moneyStr(parsed.totalIncGst),
        taxable_ex_gst: moneyStr(parsed.taxableExGst),
        gst_free_ex_gst: moneyStr(parsed.gstFreeExGst),
        gst_registered: gstRegistered,
        comment: String(fd.get("comment") || "").trim(),
        work_photos_b64: [...draftPhotos],
        status: String(draft?.status || "not_sent"),
        pdf_status: "pending",
      };
      draft = toSave;
      const savedId = await saveQuotePackage({
        quote: toSave,
        businessName,
        usedNumber: quoteNumber,
        preparePdf: true,
      });
      await flushQueue(ctx.onSyncStatus);
      clearCreateDraft();
      router.navigate("quotes", "success", { name: savedId });
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
          <p class="hint">Save keeps them in Customers. Use once is only for this quote.</p>
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
    showToast(result === "saved" ? "Customer saved." : "Customer added for this quote.", "success");
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
  const [quotes, customers] = await Promise.all([cache.getQuotes(), cache.getCustomers()]);
  const quote = quotes[key];
  if (!quote) {
    router.navigate("quotes");
    return renderQuotes(panel, ctx);
  }
  const n = Number(quote.quote_number);
  const customer = customers[String(quote.customer_name)] || {};
  const sendEmail = String(quote.customer_email || customer.email || "").trim();
  const hasEmail = Boolean(sendEmail);
  const canSend = ["not_sent", "send_failed"].includes(String(quote.status || "not_sent"));
  const kind = docKindLabel(String(quote.doc_kind || "quote"));

  panel.innerHTML = `
    <section class="panel success-panel">
      <div class="panel-header">
        <div>
          <h2>${esc(kind)} saved</h2>
          <p class="hint">#${formatInvoiceNumber(n)} · ${formatMoney(Number(quote.total_inc_gst || 0))}</p>
        </div>
        <button type="button" class="btn small ghost" id="success-edit">Edit</button>
      </div>
      <div class="pdf-embed-wrap" id="pdf-embed-wrap">
        <p class="hint pdf-embed-loading" id="pdf-embed-loading">Preparing PDF…</p>
        <iframe class="pdf-embed" id="pdf-embed" title="Quote PDF" hidden></iframe>
      </div>
      <p class="error-text" id="pdf-embed-error" hidden></p>
      <div class="btn-row stacked">
        <button type="button" class="btn secondary" id="success-download" disabled>Download PDF</button>
        <button type="button" class="btn primary" id="success-send" ${!hasEmail || !canSend ? "disabled" : ""}>Send to customer</button>
        ${!hasEmail ? `<p class="hint">Add an email to send this quote automatically.</p>` : ""}
        <button type="button" class="btn ghost" id="success-done">Done</button>
      </div>
    </section>`;

  let pdfFilename = `Quote_${formatInvoiceNumber(n)}.pdf`;

  const leaveSuccess = () => {
    revokeSuccessPdfUrl();
    router.navigate("quotes");
  };

  panel.querySelector("#success-edit")?.addEventListener("click", () => {
    revokeSuccessPdfUrl();
    loadQuoteIntoCreateDraft(quote);
    router.navigate("quotes", "create");
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
      const sendResult = await queueQuoteEmail(key);
      trackEvent("send_quote");
      await flushQueue(ctx.onSyncStatus);
      if (sendResult.finalStatus === "send_failed") {
        showToast("Send failed. Check the customer email and try again.", "error");
        return;
      }
      if (sendResult.finalStatus === "sent") {
        showToast("Quote sent.", "success");
        leaveSuccess();
        return;
      }
      revokeSuccessPdfUrl();
      router.navigate("quotes");
      void reconcileQuoteEmailSendStatus(key).then(async (status) => {
        if (status === "sent") showToast("Quote sent.", "success");
        else if (status === "send_failed") {
          showToast("Send failed. Check the customer email and try again.", "error");
        }
        await refreshQuotesListIfVisible(ctx);
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
