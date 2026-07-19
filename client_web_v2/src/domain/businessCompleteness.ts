import { isGstRegistered } from "./gst";
import type { EntityMap } from "../types";

function filled(value: unknown): boolean {
  return String(value || "").trim().length > 0;
}

/** True when name, email, address, payment details, and ABN (if GST) are present. */
export function isBusinessComplete(record: Record<string, unknown> | null | undefined): boolean {
  if (!record) return false;
  if (!filled(record.business_name)) return false;
  const email = String(record.email || "").trim();
  if (!email || !email.includes("@")) return false;
  if (
    !filled(record.address_line1) ||
    !filled(record.suburb) ||
    !filled(record.state) ||
    !filled(record.postcode)
  ) {
    return false;
  }
  if (!filled(record.account_name) || !filled(record.bsb) || !filled(record.acc)) {
    return false;
  }
  if (isGstRegistered(record)) {
    const abn = String(record.business_abn || record.abn || "").replace(/\D/g, "");
    if (!abn) return false;
  }
  return true;
}

/** Default (or first) business profile used for setup nudges. */
export function getSetupBusiness(
  businesses: EntityMap,
  settings: Record<string, unknown>
): { name: string; record: Record<string, unknown> } | null {
  const keys = Object.keys(businesses);
  if (!keys.length) return null;
  const preferred = String(settings.default_business || "").trim();
  const name = preferred && businesses[preferred] ? preferred : keys[0];
  return { name, record: businesses[name] || {} };
}

export function isSetupBusinessComplete(
  businesses: EntityMap,
  settings: Record<string, unknown>
): boolean {
  const setup = getSetupBusiness(businesses, settings);
  if (!setup) return false;
  return isBusinessComplete(setup.record);
}

const PROMPT_KEY_PREFIX = "frogswork_biz_setup_prompted_";

export function businessSetupPromptStorageKey(accountKey: string): string {
  return `${PROMPT_KEY_PREFIX}${accountKey}`;
}

export function hasSeenBusinessSetupPrompt(accountKey: string): boolean {
  if (!accountKey) return false;
  try {
    return localStorage.getItem(businessSetupPromptStorageKey(accountKey)) === "1";
  } catch {
    return false;
  }
}

export function markBusinessSetupPromptSeen(accountKey: string): void {
  if (!accountKey) return;
  try {
    localStorage.setItem(businessSetupPromptStorageKey(accountKey), "1");
  } catch {
    /* ignore quota / private mode */
  }
}
