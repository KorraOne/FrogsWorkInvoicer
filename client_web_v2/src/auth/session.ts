import type { SessionTokens } from "../types";

const ACCESS_KEY = "frogswork_access_token";
const REFRESH_KEY = "frogswork_refresh_token";

function apiBase(): string {
  const host = window.location.hostname;
  const isLocal = host === "localhost" || host === "127.0.0.1";
  const stored = localStorage.getItem("frogswork_api")?.replace(/\/$/, "");
  if (isLocal) {
    if (stored) return stored;
    return "https://api.frogswork.com";
  }
  return stored || "https://api.frogswork.com";
}

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_KEY) || "";
}

export function getRefreshToken(): string {
  return localStorage.getItem(REFRESH_KEY) || "";
}

export function saveSession(tokens: SessionTokens): void {
  if (tokens.access_token) localStorage.setItem(ACCESS_KEY, tokens.access_token);
  if (tokens.refresh_token) localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

function stripAuthParamsFromUrl(): void {
  const url = new URL(window.location.href);
  let changed = false;
  for (const key of ["handoff", "pwa_auth", "access_token", "refresh_token"]) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }
  if (changed) {
    const qs = url.searchParams.toString();
    history.replaceState(null, "", url.pathname + (qs ? `?${qs}` : "") + url.hash);
  }
}

/**
 * Capture cross-domain auth from an opaque ?handoff= code (redeemed via API).
 * Strips the code from the URL before analytics or navigation continue.
 */
export async function captureAuthFromUrl(): Promise<boolean> {
  const search = new URLSearchParams(window.location.search);
  const handoff = (search.get("handoff") || "").trim();
  if (!handoff) return false;

  stripAuthParamsFromUrl();
  try {
    const res = await fetch(`${apiBase()}/auth/handoff/redeem`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ code: handoff }),
    });
    const data = (await res.json().catch(() => ({}))) as {
      access_token?: string;
      refresh_token?: string;
      error?: string;
    };
    if (!res.ok || !data.access_token) {
      return false;
    }
    saveSession({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
    });
    return true;
  } catch {
    return false;
  }
}

export function mapLoginError(message: string): string {
  const msg = String(message || "").trim();
  if (!msg || msg === "Unauthorized") return "Invalid email or password.";
  return msg;
}
