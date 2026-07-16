import type { SessionTokens } from "../types";

const ACCESS_KEY = "frogswork_access_token";
const REFRESH_KEY = "frogswork_refresh_token";

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

export function captureAuthFromUrl(): boolean {
  const search = new URLSearchParams(window.location.search);
  if (search.get("pwa_auth") !== "1") return false;
  const access = search.get("access_token") || "";
  if (!access) return false;
  saveSession({
    access_token: access,
    refresh_token: search.get("refresh_token") || undefined,
  });
  history.replaceState(null, "", window.location.pathname || "/");
  return true;
}

export function mapLoginError(message: string): string {
  const msg = String(message || "").trim();
  if (!msg || msg === "Unauthorized") return "Invalid email or password.";
  return msg;
}
