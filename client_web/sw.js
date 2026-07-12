const CACHE = "frogswork-pwa-v5";
const ASSETS = [
  "/",
  "/index.html",
  "/css/app.css",
  "/manifest.webmanifest",
  "/js/app.js",
  "/js/api.js",
  "/js/idb.js",
  "/js/sync.js",
  "/js/router.js",
  "/js/components/forms.js",
  "/js/domain/address.js",
  "/js/domain/dashboard.js",
  "/js/domain/due_dates.js",
  "/js/domain/gst.js",
  "/js/domain/invoice_format.js",
  "/js/domain/invoices_group.js",
  "/js/views/business.js",
  "/js/views/customers.js",
  "/js/views/dashboard.js",
  "/js/views/invoice_form.js",
  "/js/views/invoices.js",
  "/js/views/settings.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
