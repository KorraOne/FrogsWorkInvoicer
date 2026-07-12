const DB_NAME = "frogswork";
const DB_VERSION = 1;

export function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      ["businesses", "customers", "invoices", "settings", "sync_queue"].forEach((store) => {
        if (!db.objectStoreNames.contains(store)) {
          db.createObjectStore(store);
        }
      });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function putJson(store, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    tx.objectStore(store).put(value, "data");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getJson(store, fallback) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).get("data");
    req.onsuccess = () => resolve(req.result ?? fallback);
    req.onerror = () => reject(req.error);
  });
}

export const cache = {
  getBusinesses: () => getJson("businesses", {}),
  saveBusinesses: (v) => putJson("businesses", v),
  getCustomers: () => getJson("customers", {}),
  saveCustomers: (v) => putJson("customers", v),
  getInvoices: () => getJson("invoices", {}),
  saveInvoices: (v) => putJson("invoices", v),
  getSettings: () => getJson("settings", {}),
  saveSettings: (v) => putJson("settings", v),
  getQueue: () => getJson("sync_queue", []),
  saveQueue: (v) => putJson("sync_queue", v),
};

export async function enqueue(type, payload) {
  const queue = await cache.getQueue();
  queue.push({ id: crypto.randomUUID(), type, payload, created_at: new Date().toISOString() });
  await cache.saveQueue(queue);
}
