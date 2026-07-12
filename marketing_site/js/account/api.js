import { API_BASE } from "./config.js";

export async function apiRequest(method, path, body, accessToken) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }
  if (!res.ok) {
    throw new Error(data.error || data.message || `Request failed (${res.status})`);
  }
  return data;
}

export function signup(email, password) {
  return apiRequest("POST", "/auth/signup", {
    email: email.trim().toLowerCase(),
    password,
  });
}

export function createCheckoutSession(tier, interval, token, promotionCode) {
  const body = { tier, interval };
  if (promotionCode) body.promotion_code = promotionCode;
  return apiRequest("POST", "/checkout/create-session", body, token);
}

export function forgotPassword(email) {
  return apiRequest("POST", "/auth/forgot-password", { email: email.trim().toLowerCase() });
}

export function resetPassword(token, password) {
  return apiRequest("POST", "/auth/reset-password", { token, password });
}

export function verifyEmail(token) {
  return apiRequest("POST", "/auth/verify-email", { token });
}

export function resendVerification(accessToken) {
  return apiRequest("POST", "/auth/resend-verification", {}, accessToken);
}

export function getCheckoutSessionInfo(sessionId) {
  const q = new URLSearchParams({ session_id: sessionId });
  return apiRequest("GET", `/checkout/session-info?${q}`);
}

export function register(password, checkoutSessionId, installId) {
  const body = { password, checkout_session_id: checkoutSessionId };
  if (installId) body.install_id = installId;
  return apiRequest("POST", "/auth/register", body);
}

export function login(email, password) {
  return apiRequest("POST", "/auth/login", {
    email: email.trim().toLowerCase(),
    password,
  });
}

export function attachCheckout(checkoutSessionId, accessToken) {
  return apiRequest(
    "POST",
    "/auth/attach-checkout",
    { checkout_session_id: checkoutSessionId },
    accessToken
  );
}

export function mapAuthError(message) {
  const text = (message || "").trim();
  if (!text) return "Something went wrong. Try again or contact support.";
  const lower = text.toLowerCase();
  if (lower.includes("invalid") && (lower.includes("password") || lower.includes("credentials"))) {
    return "Wrong email or password.";
  }
  if (lower.includes("already") && lower.includes("account")) {
    return "That email already has an account. Sign in.";
  }
  if (lower.includes("not active yet")) {
    return text;
  }
  return text;
}
