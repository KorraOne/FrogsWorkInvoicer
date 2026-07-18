import { apiRequest } from "../api/client";
import { isDesktopHost } from "./host";

const DEVICE_KEY = "frogswork_device_id";

function randomId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `d-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getOrCreateDeviceId(): string {
  try {
    const existing = localStorage.getItem(DEVICE_KEY);
    if (existing && existing.length >= 8) return existing;
    const id = randomId();
    localStorage.setItem(DEVICE_KEY, id);
    return id;
  } catch {
    return randomId();
  }
}

export function detectPlatform(): "desktop" | "browser" | "pwa" {
  if (isDesktopHost()) return "desktop";
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  if (standalone) return "pwa";
  return "browser";
}

function coarseUa(): string {
  const ua = navigator.userAgent || "";
  // Keep short coarse hint only (browser family-ish), not full fingerprint dump
  if (/Edg\//i.test(ua)) return "edge";
  if (/Chrome\//i.test(ua) && !/Edg\//i.test(ua)) return "chrome";
  if (/Firefox\//i.test(ua)) return "firefox";
  if (/Safari\//i.test(ua) && !/Chrome\//i.test(ua)) return "safari";
  if (/Android/i.test(ua)) return "android";
  if (/iPhone|iPad/i.test(ua)) return "ios";
  return "other";
}

/** Register this device with the API (no-op if logged out / offline). */
export async function reportDeviceSighting(): Promise<void> {
  try {
    await apiRequest("POST", "/devices/upsert", {
      device_id: getOrCreateDeviceId(),
      platform: detectPlatform(),
      coarse_ua: coarseUa(),
    }, true);
  } catch {
    /* non-fatal */
  }
}
