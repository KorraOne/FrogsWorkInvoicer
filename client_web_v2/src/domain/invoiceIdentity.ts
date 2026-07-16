/** Stable invoice identity — display number is not unique. */

export function newInvoiceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `inv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/** Map / D1 key for an invoice record. */
export function invoiceStorageKey(inv: Record<string, unknown>, fallbackKey?: string): string {
  const id = String(inv.invoice_id || "").trim();
  if (id) return id;
  if (fallbackKey) return fallbackKey;
  const n = parseInt(String(inv.invoice_number), 10);
  if (Number.isFinite(n) && n >= 1) return String(n).padStart(8, "0");
  return newInvoiceId();
}

/** Ensure every invoice has invoice_id; rekey map by invoice_id. */
export function normalizeInvoicesMap(
  invoices: Record<string, Record<string, unknown>> | null | undefined
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const [mapKey, inv] of Object.entries(invoices || {})) {
    if (!inv || typeof inv !== "object") continue;
    const id = invoiceStorageKey(inv, mapKey);
    const next: Record<string, unknown> = { ...inv, invoice_id: id };
    // Prefer non-deleted if two collide (shouldn't after rekey).
    if (out[id] && out[id].deleted_at && !next.deleted_at) {
      out[id] = next;
    } else if (!out[id]) {
      out[id] = next;
    }
  }
  return out;
}

export function findInvoiceNumberConflicts(
  invoices: Record<string, Record<string, unknown>>,
  invoiceNumber: number,
  businessName: string,
  excludeId?: string
): { active: number; deleted: number } {
  let active = 0;
  let deleted = 0;
  for (const inv of Object.values(invoices || {})) {
    const id = String(inv.invoice_id || "");
    if (excludeId && id === excludeId) continue;
    if (String(inv.business_name || inv.business || "") !== businessName) continue;
    if (parseInt(String(inv.invoice_number), 10) !== invoiceNumber) continue;
    if (inv.deleted_at) deleted += 1;
    else active += 1;
  }
  return { active, deleted };
}
