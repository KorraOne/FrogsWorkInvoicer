import { api } from "./api.js";
import { cache, enqueue } from "./idb.js";

async function syncMutation(type, payload) {
  try {
    await api.sync([{ type, payload }]);
  } catch {
    await enqueue(type, payload);
  }
}

export async function pullBootstrap() {
  const data = await api.bootstrap();
  if (data.businesses) await cache.saveBusinesses(data.businesses);
  if (data.customers) await cache.saveCustomers(data.customers);
  if (data.invoices) await cache.saveInvoices(data.invoices);
  if (data.settings) await cache.saveSettings(data.settings);
  localStorage.setItem("frogswork_last_sync", new Date().toISOString());
  return data;
}

export async function flushQueue(onStatus) {
  const queue = await cache.getQueue();
  if (!queue.length) return { flushed: 0 };
  if (onStatus) onStatus(`Syncing ${queue.length} change(s)…`);
  const mutations = queue.map((item) => ({ type: item.type, payload: item.payload }));
  const result = await api.sync(mutations);
  await cache.saveQueue([]);
  localStorage.setItem("frogswork_last_sync", new Date().toISOString());
  if (onStatus) onStatus("");
  return { flushed: queue.length, result };
}

export async function upsertCustomer(name, record) {
  const customers = await cache.getCustomers();
  customers[name] = record;
  await cache.saveCustomers(customers);
  await syncMutation("upsert_customer", { customers: { [name]: record } });
}

export async function deleteCustomer(name) {
  const customers = await cache.getCustomers();
  delete customers[name];
  await cache.saveCustomers(customers);
  await syncMutation("delete_customer", { name });
}

export async function upsertBusiness(name, record) {
  const businesses = await cache.getBusinesses();
  businesses[name] = record;
  await cache.saveBusinesses(businesses);
  await syncMutation("upsert_business", { businesses: { [name]: record } });
}

export async function deleteBusiness(name) {
  const businesses = await cache.getBusinesses();
  delete businesses[name];
  await cache.saveBusinesses(businesses);
  await syncMutation("upsert_business", { businesses: { [name]: null } });
}

export async function upsertSettings(partial) {
  const settings = await cache.getSettings();
  const merged = { ...settings, ...partial };
  await cache.saveSettings(merged);
  await syncMutation("upsert_settings", { settings: partial });
}

export async function createInvoiceOffline(invoice) {
  const invoices = await cache.getInvoices();
  const key = String(invoice.invoice_number).padStart(8, "0");
  invoice.pdf_status = invoice.pdf_status || "pending";
  invoice.status = invoice.status || "not_sent";
  invoices[key] = invoice;
  await cache.saveInvoices(invoices);
  await syncMutation("create_invoice", { invoice });
}

export async function updateInvoiceStatus(invoiceNumber, status) {
  const invoices = await cache.getInvoices();
  const key = String(invoiceNumber).padStart(8, "0");
  if (invoices[key]) {
    invoices[key].status = status;
    if (status === "paid") invoices[key].paid_date = new Date().toISOString().slice(0, 10);
    if (status === "sent") invoices[key].sent_date = new Date().toISOString().slice(0, 10);
    await cache.saveInvoices(invoices);
  }
  await syncMutation("update_invoice_status", { invoice_number: invoiceNumber, status });
}

export async function softDeleteInvoice(invoiceNumber) {
  const invoices = await cache.getInvoices();
  const key = String(invoiceNumber).padStart(8, "0");
  if (invoices[key]) {
    invoices[key].deleted_at = new Date().toISOString();
    await cache.saveInvoices(invoices);
  }
  await syncMutation("delete_invoice", { invoice_number: invoiceNumber });
}

export async function queueEmailSend(invoiceNumber, { autoSendAllowed = true } = {}) {
  if (!autoSendAllowed) {
    throw new Error("Automatic send requires an active paid subscription.");
  }
  const invoices = await cache.getInvoices();
  const key = String(invoiceNumber).padStart(8, "0");
  if (invoices[key]) {
    invoices[key].status = "send_queued";
    await cache.saveInvoices(invoices);
  }
  await syncMutation("enqueue_email_send", { invoice_number: invoiceNumber });
}

export async function bumpInvoiceCounter(businessName, usedNumber) {
  const businesses = await cache.getBusinesses();
  if (!businesses[businessName]) return;
  const current = parseInt(businesses[businessName].invoice_counter, 10) || 1;
  businesses[businessName].invoice_counter = Math.max(current, usedNumber + 1);
  await cache.saveBusinesses(businesses);
  await syncMutation("upsert_business", { businesses: { [businessName]: businesses[businessName] } });
}
