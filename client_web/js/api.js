function getApiBase() {

  const host = window.location.hostname;

  const isLocal = host === "localhost" || host === "127.0.0.1";

  const stored = localStorage.getItem("frogswork_api")?.replace(/\/$/, "");

  if (isLocal) {

    if (stored && !stored.includes("api.frogswork.com")) return stored;

    return "http://127.0.0.1:8787";

  }

  return stored || "https://api.frogswork.com";

}



function authToken() {
  return localStorage.getItem("frogswork_access_token") || "";
}



function headers(auth = false) {

  const h = { Accept: "application/json", "Content-Type": "application/json" };

  if (auth) {

    const token = authToken();

    if (token) h.Authorization = `Bearer ${token}`;

  }

  return h;

}



async function refreshTokens() {

  const refresh = localStorage.getItem("frogswork_refresh_token");

  if (!refresh) return false;

  const base = getApiBase();

  const res = await fetch(`${base}/auth/refresh`, {

    method: "POST",

    headers: headers(false),

    body: JSON.stringify({ refresh_token: refresh }),

  });

  if (!res.ok) return false;

  const data = await res.json();

  if (data.access_token) {

    localStorage.setItem("frogswork_access_token", data.access_token);

    if (data.refresh_token) localStorage.setItem("frogswork_refresh_token", data.refresh_token);

    return true;

  }

  return false;

}



function clearStoredSession() {
  localStorage.removeItem("frogswork_access_token");
  localStorage.removeItem("frogswork_refresh_token");
  localStorage.removeItem("frogswork_guest_token");
}

async function request(method, path, body, auth = false, retried = false) {

  const base = getApiBase();

  let res;

  try {

    res = await fetch(`${base}${path}`, {

      method,

      headers: headers(auth),

      body: body ? JSON.stringify(body) : undefined,

    });

  } catch {

    throw new Error(`Cannot reach API at ${base}. Run .\\scripts\\start-pwa-dev.ps1 and reload.`);

  }

  if (res.status === 401 && auth && !retried && localStorage.getItem("frogswork_refresh_token")) {

    const ok = await refreshTokens();

    if (ok) return request(method, path, body, auth, true);

    clearStoredSession();

  }

  const text = await res.text();

  let data = {};

  if (text) {

    try {

      data = JSON.parse(text);

    } catch {

      data = { error: text };

    }

  }

  if (!res.ok) throw new Error(data.error || res.statusText);

  return data;

}



export const api = {

  setBase(url) {

    localStorage.setItem("frogswork_api", url);

  },

  getBase() {

    return getApiBase();

  },

  login(email, password) {

    return request("POST", "/auth/login", { email, password });

  },

  mapLoginError(message) {
    const msg = String(message || "").trim();
    if (!msg || msg === "Unauthorized") return "Invalid email or password.";
    return msg;
  },

  refresh() {

    const token = localStorage.getItem("frogswork_refresh_token");

    return request("POST", "/auth/refresh", { refresh_token: token });

  },

  resendVerification() {

    return request("POST", "/auth/resend-verification", {}, true);

  },

  entitlements: () => request("GET", "/entitlements", null, true),

  bootstrap: () => request("GET", "/documents/bootstrap", null, true),

  sync: (mutations) => request("POST", "/documents/sync", { mutations }, true),

  generatePdf: (invoiceNumber) =>

    request("POST", `/documents/invoices/${invoiceNumber}/generate`, {}, true),

  sendInvoice: (invoiceNumber) =>

    request("POST", `/documents/invoices/${invoiceNumber}/send`, {}, true),

  async getInvoicePdf(invoiceNumber) {

    return request("GET", `/documents/invoices/${invoiceNumber}/pdf`, null, true);

  },

  clearSession() {
    clearStoredSession();
  },

  saveSession(tokens) {
    if (tokens?.access_token) {
      localStorage.setItem("frogswork_access_token", tokens.access_token);
    }
    if (tokens?.refresh_token) {
      localStorage.setItem("frogswork_refresh_token", tokens.refresh_token);
    }
    localStorage.removeItem("frogswork_guest_token");
  },

};


