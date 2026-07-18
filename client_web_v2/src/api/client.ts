import { clearSession, getAccessToken, getRefreshToken, saveSession } from "../auth/session";
import { desktopHostConfig } from "../lib/host";

function getApiBase(): string {
  const fromHost = desktopHostConfig()?.apiBase?.replace(/\/$/, "");
  if (fromHost) return fromHost;

  const host = window.location.hostname;
  const isLocal = host === "localhost" || host === "127.0.0.1";
  const stored = localStorage.getItem("frogswork_api")?.replace(/\/$/, "");
  if (isLocal) {
    // Prefer explicit override (incl. production API) for local UI debugging.
    if (stored) return stored;
    return "https://api.frogswork.com";
  }
  return stored || "https://api.frogswork.com";
}

async function refreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  const base = getApiBase();
  const res = await fetch(`${base}/auth/refresh`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return false;
  const data = (await res.json()) as { access_token?: string; refresh_token?: string };
  if (!data.access_token) return false;
  saveSession({ access_token: data.access_token, refresh_token: data.refresh_token });
  return true;
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
  auth = false,
  retried = false
): Promise<T> {
  const base = getApiBase();
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (auth) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(`Cannot reach API at ${base}.`);
  }
  if (res.status === 401 && auth && !retried && getRefreshToken()) {
    const ok = await refreshTokens();
    if (ok) return apiRequest(method, path, body, auth, true);
    clearSession();
  }
  const text = await res.text();
  let data: { error?: string } = {};
  if (text) {
    try {
      data = JSON.parse(text) as { error?: string };
    } catch {
      data = { error: text };
    }
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data as T;
}

export function getBaseUrl(): string {
  return getApiBase();
}

/** Authenticated binary download (e.g. account export ZIP). */
export async function apiDownload(path: string, retried = false): Promise<Blob> {
  const base = getApiBase();
  const headers: Record<string, string> = { Accept: "application/zip, application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { method: "GET", headers });
  } catch {
    throw new Error(`Cannot reach API at ${base}.`);
  }
  if (res.status === 401 && !retried && getRefreshToken()) {
    const ok = await refreshTokens();
    if (ok) return apiDownload(path, true);
    clearSession();
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = (await res.json()) as { error?: string };
      if (data.error) message = data.error;
    } catch {
      /* ignore */
    }
    throw new Error(message || "Download failed.");
  }
  return res.blob();
}
