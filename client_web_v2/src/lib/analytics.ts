/**
 * Light GA4 for the Cloud app (Frogs Work App / app.frogswork.com).
 * Override with VITE_GA4_MEASUREMENT_ID at build time if needed.
 * Never send emails, invoice content, customer names, or other PII.
 */

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const DEFAULT_MEASUREMENT_ID = "G-MV6WQ3Z369";
const MEASUREMENT_ID = String(
  import.meta.env.VITE_GA4_MEASUREMENT_ID || DEFAULT_MEASUREMENT_ID
).trim();
let ready = false;

export function initCloudAnalytics() {
  if (!MEASUREMENT_ID || !MEASUREMENT_ID.startsWith("G-")) return;
  if (ready) return;

  window.dataLayer = window.dataLayer || [];
  // gtag.js only processes `arguments` objects pushed to dataLayer; plain arrays are ignored.
  window.gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer!.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID, {
    anonymize_ip: true,
    send_page_view: false,
  });

  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
  s.onload = () => {
    ready = true;
  };
  document.head.appendChild(s);
}

export function trackEvent(name: string, params?: Record<string, string | number | boolean>) {
  if (!MEASUREMENT_ID || !window.gtag || !name) return;
  const safe: Record<string, string | number | boolean> = {};
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
        safe[k] = v;
      }
    }
  }
  window.gtag("event", name, safe);
}

export function trackScreen(screenName: string) {
  trackEvent("page_view", { page_title: screenName, screen_name: screenName });
}
