import { normalizeInvoicesMap } from "../domain/invoiceIdentity";
import { normalizeQuotesMap } from "../domain/quoteIdentity";

const DB_NAME = "frogswork_v2";
const DB_VERSION = 2;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const store of ["businesses", "customers", "invoices", "quotes", "settings", "sync_queue"]) {
        if (!db.objectStoreNames.contains(store)) db.createObjectStore(store);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function putJson<T>(store: string, value: T): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value, "data");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getJson<T>(store: string, fallback: T): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).get("data");
    req.onsuccess = () => resolve((req.result as T) ?? fallback);
    req.onerror = () => reject(req.error);
  });
}

export const cache = {
  getBusinesses: () => getJson("businesses", {} as Record<string, Record<string, unknown>>),
  saveBusinesses: (v: Record<string, Record<string, unknown>>) => putJson("businesses", v),
  getCustomers: () => getJson("customers", {} as Record<string, Record<string, unknown>>),
  saveCustomers: (v: Record<string, Record<string, unknown>>) => putJson("customers", v),
  getInvoices: async () =>
    normalizeInvoicesMap(await getJson("invoices", {} as Record<string, Record<string, unknown>>)),
  saveInvoices: (v: Record<string, Record<string, unknown>>) =>
    putJson("invoices", normalizeInvoicesMap(v)),
  getQuotes: async () =>
    normalizeQuotesMap(await getJson("quotes", {} as Record<string, Record<string, unknown>>)),
  saveQuotes: (v: Record<string, Record<string, unknown>>) =>
    putJson("quotes", normalizeQuotesMap(v)),
  getSettings: () => getJson("settings", {} as Record<string, unknown>),
  saveSettings: (v: Record<string, unknown>) => putJson("settings", v),
  getQueue: () =>
    getJson(
      "sync_queue",
      [] as Array<{ id: string; type: string; payload: Record<string, unknown>; created_at?: string }>
    ),
  saveQueue: (v: Array<{ id: string; type: string; payload: Record<string, unknown>; created_at?: string }>) =>
    putJson("sync_queue", v),
  clearAll: async () => {
    await putJson("businesses", {});
    await putJson("customers", {});
    await putJson("invoices", {});
    await putJson("quotes", {});
    await putJson("settings", {});
    await putJson("sync_queue", []);
  },
};

export async function enqueue(type: string, payload: Record<string, unknown>) {
  const queue = await cache.getQueue();
  queue.push({
    id: crypto.randomUUID(),
    type,
    payload,
    created_at: new Date().toISOString(),
  });
  await cache.saveQueue(queue);
}
