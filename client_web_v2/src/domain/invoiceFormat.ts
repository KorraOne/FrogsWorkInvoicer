export function round2(n: number): number {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

export function formatMoney(amount: number | string): string {
  const n = Number(amount) || 0;
  return `$${n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatInvoiceNumber(number: number | string): string {
  return String(Math.max(1, parseInt(String(number), 10) || 0)).padStart(8, "0");
}

export function parseInvoiceNumberInput(raw: string): number {
  const digits = String(raw || "").replace(/\D/g, "");
  if (!digits) throw new Error("Enter an invoice number.");
  const number = parseInt(digits, 10);
  if (number < 1) throw new Error("Invoice number must be at least 1.");
  return number;
}

export function suggestedInvoiceNumber(
  businessName: string,
  businessProfile: Record<string, unknown>,
  invoices: Record<string, Record<string, unknown>>
): number {
  const counter = parseInt(String(businessProfile?.invoice_counter), 10) || 1;
  const matching = Object.values(invoices || {})
    .filter((inv) => !inv.deleted_at && String(inv.business_name || inv.business || "") === businessName)
    .map((inv) => parseInt(String(inv.invoice_number), 10) || 0);
  const deletedMatching = Object.values(invoices || {})
    .filter((inv) => inv.deleted_at && String(inv.business_name || inv.business || "") === businessName)
    .map((inv) => parseInt(String(inv.invoice_number), 10) || 0);
  // Include deleted so soft-delete does not free a number for default suggestion.
  const allUsed = [...matching, ...deletedMatching];
  return !allUsed.length ? counter : Math.max(counter, Math.max(...allUsed) + 1);
}

export function formatInvoiceDate(isoDate: string): string {
  if (!isoDate) return "";
  const d = new Date(isoDate + "T12:00:00");
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function moneyStr(n: number): string {
  return round2(n).toFixed(2);
}
