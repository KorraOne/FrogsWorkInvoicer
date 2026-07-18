import { apiDownload, apiRequest } from "./client";
import type { MobileAccount, SessionTokens } from "../types";

export interface SessionResponse extends SessionTokens {
  account: MobileAccount;
}

export interface BootstrapData {
  businesses: Record<string, Record<string, unknown>>;
  customers: Record<string, Record<string, unknown>>;
  invoices: Record<string, Record<string, unknown>>;
  settings: Record<string, unknown>;
}

export function loginSession(email: string, password: string): Promise<SessionResponse> {
  return apiRequest<SessionResponse>("POST", "/mobile/v1/session", { email, password });
}

export function fetchAccount(): Promise<MobileAccount> {
  return apiRequest<MobileAccount>("GET", "/mobile/v1/account", undefined, true);
}

export function fetchBootstrap(): Promise<BootstrapData> {
  return apiRequest<BootstrapData>("GET", "/mobile/v1/bootstrap", undefined, true);
}

export function postSync(mutations: Array<{ type: string; payload: Record<string, unknown> }>) {
  return apiRequest<{ ok: boolean; results?: unknown[]; errors?: unknown[] }>(
    "POST",
    "/mobile/v1/sync",
    { mutations },
    true
  );
}

export function fetchInvoicePdf(invoiceId: string) {
  const id = encodeURIComponent(String(invoiceId || "").trim());
  return apiRequest<{ filename: string; content_b64: string; invoice_key?: string }>(
    "GET",
    `/mobile/v1/invoices/${id}/pdf`,
    undefined,
    true
  );
}

export function resendVerification() {
  return apiRequest("POST", "/auth/resend-verification", {}, true);
}

export function downloadAccountExport() {
  return apiDownload("/account/export");
}

export function deleteAccountData() {
  return apiRequest<{ ok: boolean }>(
    "POST",
    "/account/data/delete",
    { confirm: "DELETE DATA" },
    true
  );
}

export function deleteAccount(password: string) {
  return apiRequest<{ ok: boolean }>(
    "POST",
    "/account/delete",
    { confirm: "DELETE ACCOUNT", password },
    true
  );
}
