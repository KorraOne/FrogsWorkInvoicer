import { fetchBootstrap, postSync } from "../api/mobile";
import { businessRecordForSync } from "../components/logoEditor";
import { newInvoiceId, normalizeInvoicesMap, invoiceStorageKey } from "../domain/invoiceIdentity";
import { newQuoteId, normalizeQuotesMap, quoteStorageKey } from "../domain/quoteIdentity";
import { cache, enqueue } from "./idb";

type Mutation = { type: string; payload: Record<string, unknown> };
type QueueItem = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at?: string;
};

function sanitizeSyncPayload(type: string, payload: Record<string, unknown>): Record<string, unknown> {
  if (type !== "upsert_business") return payload;
  const businesses = payload.businesses as Record<string, Record<string, unknown>> | undefined;
  if (!businesses) return payload;
  const trimmed: Record<string, Record<string, unknown>> = {};
  for (const [name, record] of Object.entries(businesses)) {
    trimmed[name] = businessRecordForSync(record);
  }
  return { ...payload, businesses: trimmed };
}

/** Merge duplicate queued mutations so retries do not multiply large payloads. */
function coalesceQueue(queue: QueueItem[]): QueueItem[] {
  const businessRecords = new Map<string, Record<string, unknown>>();
  const customerRecords = new Map<string, Record<string, unknown>>();
  const settingsPartials: Record<string, unknown>[] = [];
  const rest: QueueItem[] = [];

  for (const item of queue) {
    if (item.type === "upsert_business") {
      const businesses = item.payload.businesses as Record<string, Record<string, unknown>> | undefined;
      for (const [name, record] of Object.entries(businesses || {})) {
        businessRecords.set(name, record);
      }
      continue;
    }
    if (item.type === "upsert_customer") {
      const customers = item.payload.customers as Record<string, Record<string, unknown>> | undefined;
      for (const [name, record] of Object.entries(customers || {})) {
        customerRecords.set(name, record);
      }
      continue;
    }
    if (item.type === "upsert_settings") {
      const partial = item.payload.settings as Record<string, unknown> | undefined;
      if (partial) settingsPartials.push(partial);
      continue;
    }
    rest.push(item);
  }

  const merged: QueueItem[] = [...rest];
  if (businessRecords.size) {
    merged.unshift({
      id: "coalesced-business",
      type: "upsert_business",
      payload: { businesses: Object.fromEntries(businessRecords) },
    });
  }
  if (customerRecords.size) {
    merged.unshift({
      id: "coalesced-customer",
      type: "upsert_customer",
      payload: { customers: Object.fromEntries(customerRecords) },
    });
  }
  if (settingsPartials.length) {
    merged.unshift({
      id: "coalesced-settings",
      type: "upsert_settings",
      payload: { settings: Object.assign({}, ...settingsPartials) },
    });
  }
  return merged;
}

async function syncMutations(mutations: Mutation[]) {
  if (!mutations.length) return null;
  const sanitized = mutations.map((m) => ({
    type: m.type,
    payload: sanitizeSyncPayload(m.type, m.payload),
  }));
  try {
    return await postSync(sanitized);
  } catch {
    for (const m of sanitized) {
      await enqueue(m.type, m.payload);
    }
    return null;
  }
}

async function syncMutation(type: string, payload: Record<string, unknown>) {
  return syncMutations([{ type, payload }]);
}

export async function pullBootstrap() {
  const data = await fetchBootstrap();
  if (data.businesses) {
    const local = await cache.getBusinesses();
    const merged: Record<string, Record<string, unknown>> = { ...data.businesses };
    for (const [name, remote] of Object.entries(merged)) {
      const localRec = local[name];
      const localSource = localRec && String(localRec.logo_source_b64 || "").trim();
      if (localSource && !String(remote.logo_source_b64 || "").trim()) {
        merged[name] = { ...remote, logo_source_b64: localSource };
      }
    }
    await cache.saveBusinesses(merged);
  }
  if (data.customers) await cache.saveCustomers(data.customers);
  if (data.invoices) await cache.saveInvoices(normalizeInvoicesMap(data.invoices));
  if (data.quotes) await cache.saveQuotes(normalizeQuotesMap(data.quotes));
  if (data.settings) await cache.saveSettings(data.settings);
  localStorage.setItem("frogswork_last_sync", new Date().toISOString());
  return data;
}

export async function flushQueue(onStatus?: (text: string) => void) {
  let queue = await cache.getQueue();
  if (!queue.length) return { flushed: 0, ok: true as const };
  queue = coalesceQueue(queue);
  await cache.saveQueue(queue);
  onStatus?.(`Syncing ${queue.length} change(s)…`);
  try {
    const mutations = queue.map((item) => ({
      type: item.type,
      payload: sanitizeSyncPayload(item.type, item.payload),
    }));
    const result = await postSync(mutations);
    await cache.saveQueue([]);
    localStorage.setItem("frogswork_last_sync", new Date().toISOString());
    onStatus?.("");
    return { flushed: queue.length, result, ok: true as const };
  } catch (ex) {
    onStatus?.("");
    const message = ex instanceof Error ? ex.message : "Sync failed.";
    return { flushed: 0, ok: false as const, error: message };
  }
}

export async function upsertCustomer(name: string, record: Record<string, unknown>) {
  const customers = await cache.getCustomers();
  customers[name] = record;
  await cache.saveCustomers(customers);
  await syncMutation("upsert_customer", { customers: { [name]: record } });
}

export async function deleteCustomer(name: string) {
  const customers = await cache.getCustomers();
  delete customers[name];
  await cache.saveCustomers(customers);
  await syncMutation("delete_customer", { name });
}

export async function upsertBusiness(name: string, record: Record<string, unknown>) {
  const businesses = await cache.getBusinesses();
  businesses[name] = record;
  await cache.saveBusinesses(businesses);
  await syncMutation("upsert_business", {
    businesses: { [name]: businessRecordForSync(record) },
  });
}

export async function upsertSettings(partial: Record<string, unknown>) {
  const settings = await cache.getSettings();
  const merged = { ...settings, ...partial };
  await cache.saveSettings(merged);
  await syncMutation("upsert_settings", { settings: partial });
}

export async function createInvoice(
  invoice: Record<string, unknown>,
  opts: { preparePdf?: boolean; sync?: boolean } = {}
) {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const invoiceId = String(invoice.invoice_id || "").trim() || newInvoiceId();
  const stored = {
    ...invoice,
    invoice_id: invoiceId,
    pdf_status: invoice.pdf_status || "pending",
    status: invoice.status || "not_sent",
  };
  invoices[invoiceId] = stored;
  await cache.saveInvoices(invoices);
  if (opts.sync !== false) {
    await syncMutation("create_invoice", {
      invoice: stored,
      prepare_pdf: Boolean(opts.preparePdf),
    });
  }
  return invoiceId;
}

/** One round-trip: create/upsert invoice + bump counter + due settings. */
export async function saveInvoicePackage(opts: {
  invoice: Record<string, unknown>;
  businessName: string;
  usedNumber: number;
  settingsPartial: Record<string, unknown>;
  preparePdf?: boolean;
}): Promise<string> {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const invoiceId = String(opts.invoice.invoice_id || "").trim() || newInvoiceId();
  const stored = {
    ...opts.invoice,
    invoice_id: invoiceId,
    pdf_status: opts.invoice.pdf_status || "pending",
    status: opts.invoice.status || "not_sent",
  };
  invoices[invoiceId] = stored;
  await cache.saveInvoices(invoices);

  const businesses = await cache.getBusinesses();
  const bizName = opts.businessName;
  if (businesses[bizName]) {
    const current = parseInt(String(businesses[bizName].invoice_counter), 10) || 1;
    businesses[bizName].invoice_counter = Math.max(current, opts.usedNumber + 1);
    await cache.saveBusinesses(businesses);
  }

  const settings = await cache.getSettings();
  await cache.saveSettings({ ...settings, ...opts.settingsPartial });

  const mutations: Mutation[] = [
    {
      type: "create_invoice",
      payload: { invoice: stored, prepare_pdf: Boolean(opts.preparePdf) },
    },
  ];
  if (businesses[bizName]) {
    mutations.push({
      type: "upsert_business",
      payload: { businesses: { [bizName]: businessRecordForSync(businesses[bizName]) } },
    });
  }
  mutations.push({ type: "upsert_settings", payload: { settings: opts.settingsPartial } });

  await syncMutations(mutations);
  return invoiceId;
}

export async function updateInvoiceStatus(invoiceId: string, status: string) {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const key = String(invoiceId || "").trim();
  const inv = invoices[key];
  if (inv) {
    inv.status = status;
    if (status === "paid") inv.paid_date = new Date().toISOString().slice(0, 10);
    else if (["not_sent", "sent", "send_queued", "send_failed"].includes(status)) {
      delete inv.paid_date;
    }
    if (status === "sent") inv.sent_date = new Date().toISOString().slice(0, 10);
    await cache.saveInvoices(invoices);
  }
  await syncMutation("update_invoice_status", {
    invoice_id: key,
    invoice_number: inv ? Number(inv.invoice_number) : undefined,
    status,
    paid_date: status === "paid" && inv ? inv.paid_date : undefined,
  });
}

export async function softDeleteInvoice(invoiceId: string) {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const key = String(invoiceId || "").trim();
  if (invoices[key]) {
    invoices[key].deleted_at = new Date().toISOString();
    await cache.saveInvoices(invoices);
  }
  await syncMutation("delete_invoice", {
    invoice_id: key,
    invoice_number: invoices[key] ? Number(invoices[key].invoice_number) : undefined,
  });
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Poll bootstrap until invoice reaches sent/send_failed (async email path). */
export async function reconcileEmailSendStatus(
  invoiceId: string,
  opts: { attempts?: number; intervalMs?: number } = {}
): Promise<string> {
  const key = String(invoiceId || "").trim();
  const attempts = opts.attempts ?? 10;
  const intervalMs = opts.intervalMs ?? 1500;
  for (let i = 0; i < attempts; i++) {
    if (i > 0) await sleep(intervalMs);
    try {
      await pullBootstrap();
    } catch {
      continue;
    }
    const invoices = normalizeInvoicesMap(await cache.getInvoices());
    const status = String(invoices[key]?.status || "").trim();
    if (status === "sent" || status === "send_failed") return status;
  }
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  return String(invoices[key]?.status || "send_queued").trim();
}

export async function queueEmailSend(invoiceId: string) {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const key = String(invoiceId || "").trim();
  if (invoices[key]) {
    invoices[key].status = "send_queued";
    await cache.saveInvoices(invoices);
  }
  const result = await syncMutation("enqueue_email_send", {
    invoice_id: key,
    invoice_number: invoices[key] ? Number(invoices[key].invoice_number) : undefined,
  });
  const first = Array.isArray(result?.results)
    ? (result!.results as Record<string, unknown>[])[0]
    : null;
  const finalStatus = String(first?.status || "send_queued").trim() || "send_queued";
  if (invoices[key]) {
    invoices[key].status = finalStatus;
    await cache.saveInvoices(invoices);
  }
  return { result, finalStatus };
}

/** Queue a payment follow-up email without changing invoice status. */
export async function queueFollowupEmail(invoiceId: string) {
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const key = String(invoiceId || "").trim();
  const result = await syncMutation("enqueue_followup_email", {
    invoice_id: key,
    invoice_number: invoices[key] ? Number(invoices[key].invoice_number) : undefined,
  });
  if (Array.isArray(result?.errors) && result!.errors.length) {
    const firstErr = result!.errors[0] as { error?: string };
    throw new Error(String(firstErr?.error || "Follow-up failed."));
  }
  const first = Array.isArray(result?.results)
    ? (result!.results as Record<string, unknown>[])[0]
    : null;
  const finalStatus = String(first?.status || "queued").trim() || "queued";
  return { result, finalStatus };
}

export async function bumpInvoiceCounter(businessName: string, usedNumber: number) {
  const businesses = await cache.getBusinesses();
  if (!businesses[businessName]) return;
  const current = parseInt(String(businesses[businessName].invoice_counter), 10) || 1;
  businesses[businessName].invoice_counter = Math.max(current, usedNumber + 1);
  await cache.saveBusinesses(businesses);
  await syncMutation("upsert_business", {
    businesses: { [businessName]: businessRecordForSync(businesses[businessName]) },
  });
}

export async function createQuote(
  quote: Record<string, unknown>,
  opts: { preparePdf?: boolean; sync?: boolean } = {}
) {
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const quoteId = String(quote.quote_id || "").trim() || newQuoteId();
  const stored = {
    ...quote,
    quote_id: quoteId,
    pdf_status: quote.pdf_status || "pending",
    status: quote.status || "not_sent",
  };
  quotes[quoteId] = stored;
  await cache.saveQuotes(quotes);
  if (opts.sync !== false) {
    await syncMutation("create_quote", {
      quote: stored,
      prepare_pdf: Boolean(opts.preparePdf),
    });
  }
  return quoteId;
}

/** Create/upsert quote + bump quote_counter on business (no due settings). */
export async function saveQuotePackage(opts: {
  quote: Record<string, unknown>;
  businessName: string;
  usedNumber: number;
  preparePdf?: boolean;
}): Promise<string> {
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const quoteId = String(opts.quote.quote_id || "").trim() || newQuoteId();
  const stored = {
    ...opts.quote,
    quote_id: quoteId,
    pdf_status: opts.quote.pdf_status || "pending",
    status: opts.quote.status || "not_sent",
  };
  quotes[quoteId] = stored;
  await cache.saveQuotes(quotes);

  const businesses = await cache.getBusinesses();
  const bizName = opts.businessName;
  if (businesses[bizName]) {
    const current = parseInt(String(businesses[bizName].quote_counter), 10) || 1;
    businesses[bizName].quote_counter = Math.max(current, opts.usedNumber + 1);
    await cache.saveBusinesses(businesses);
  }

  const mutations: Mutation[] = [
    {
      type: "create_quote",
      payload: { quote: stored, prepare_pdf: Boolean(opts.preparePdf) },
    },
  ];
  if (businesses[bizName]) {
    mutations.push({
      type: "upsert_business",
      payload: { businesses: { [bizName]: businessRecordForSync(businesses[bizName]) } },
    });
  }

  await syncMutations(mutations);
  return quoteId;
}

export async function updateQuoteStatus(
  quoteId: string,
  status: string,
  extra: Record<string, unknown> = {}
) {
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const key = String(quoteId || "").trim();
  const quote = quotes[key];
  if (quote) {
    quote.status = status;
    if (status === "sent" && !quote.sent_date) {
      quote.sent_date = new Date().toISOString().slice(0, 10);
    }
    Object.assign(quote, extra);
    await cache.saveQuotes(quotes);
  }
  await syncMutation("update_quote_status", {
    quote_id: key,
    quote_number: quote ? Number(quote.quote_number) : undefined,
    status,
    ...extra,
  });
}

export async function softDeleteQuote(quoteId: string) {
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const key = String(quoteId || "").trim();
  if (quotes[key]) {
    quotes[key].deleted_at = new Date().toISOString();
    await cache.saveQuotes(quotes);
  }
  await syncMutation("delete_quote", {
    quote_id: key,
    quote_number: quotes[key] ? Number(quotes[key].quote_number) : undefined,
  });
}

/** Poll bootstrap until quote reaches sent/send_failed (async email path). */
export async function reconcileQuoteEmailSendStatus(
  quoteId: string,
  opts: { attempts?: number; intervalMs?: number } = {}
): Promise<string> {
  const key = String(quoteId || "").trim();
  const attempts = opts.attempts ?? 10;
  const intervalMs = opts.intervalMs ?? 1500;
  for (let i = 0; i < attempts; i++) {
    if (i > 0) await sleep(intervalMs);
    try {
      await pullBootstrap();
    } catch {
      continue;
    }
    const quotes = normalizeQuotesMap(await cache.getQuotes());
    const status = String(quotes[key]?.status || "").trim();
    if (status === "sent" || status === "send_failed") return status;
  }
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  return String(quotes[key]?.status || "send_queued").trim();
}

export async function queueQuoteEmail(quoteId: string) {
  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const key = String(quoteId || "").trim();
  if (quotes[key]) {
    quotes[key].status = "send_queued";
    await cache.saveQuotes(quotes);
  }
  const result = await syncMutation("enqueue_quote_email", {
    quote_id: key,
    quote_number: quotes[key] ? Number(quotes[key].quote_number) : undefined,
  });
  const first = Array.isArray(result?.results)
    ? (result!.results as Record<string, unknown>[])[0]
    : null;
  const finalStatus = String(first?.status || "send_queued").trim() || "send_queued";
  if (quotes[key]) {
    quotes[key].status = finalStatus;
    await cache.saveQuotes(quotes);
  }
  return { result, finalStatus };
}

/**
 * Locally create invoice + mark quote converted, then sync convert_quote_to_invoice.
 * Optionally bumps invoice_counter on the business.
 */
export async function convertQuoteToInvoice(
  quoteId: string,
  invoicePayload: Record<string, unknown>,
  opts: { preparePdf?: boolean; businessName?: string; usedInvoiceNumber?: number } = {}
): Promise<string> {
  const invoiceId = await createInvoice(invoicePayload, { preparePdf: false, sync: false });
  const invoices = normalizeInvoicesMap(await cache.getInvoices());
  const stored = invoices[invoiceId];

  const quotes = normalizeQuotesMap(await cache.getQuotes());
  const qKey = String(quoteId || "").trim();
  if (quotes[qKey]) {
    quotes[qKey].status = "converted";
    quotes[qKey].converted_invoice_id = invoiceId;
    quotes[qKey].converted_invoice_number =
      stored?.invoice_number ?? invoicePayload.invoice_number;
    await cache.saveQuotes(quotes);
  }

  const mutations: Mutation[] = [
    {
      type: "convert_quote_to_invoice",
      payload: {
        quote_id: qKey,
        quote_number: quotes[qKey] ? Number(quotes[qKey].quote_number) : undefined,
        invoice: stored,
        prepare_pdf: Boolean(opts.preparePdf),
        converted_invoice_number:
          stored?.invoice_number ?? invoicePayload.invoice_number,
      },
    },
  ];

  const bizName = opts.businessName || String(stored?.business_name || "").trim();
  const usedNumber =
    opts.usedInvoiceNumber ??
    (stored ? parseInt(String(stored.invoice_number), 10) : NaN);
  if (bizName && Number.isFinite(usedNumber)) {
    const businesses = await cache.getBusinesses();
    if (businesses[bizName]) {
      const current = parseInt(String(businesses[bizName].invoice_counter), 10) || 1;
      businesses[bizName].invoice_counter = Math.max(current, usedNumber + 1);
      await cache.saveBusinesses(businesses);
      mutations.push({
        type: "upsert_business",
        payload: { businesses: { [bizName]: businessRecordForSync(businesses[bizName]) } },
      });
    }
  }

  await syncMutations(mutations);
  return invoiceId;
}

export { invoiceStorageKey, newInvoiceId, quoteStorageKey, newQuoteId };
