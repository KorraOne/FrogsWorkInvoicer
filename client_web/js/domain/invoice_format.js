/** Decimal-safe money helpers. */
export function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

export function parseAmount(raw) {
  const cleaned = String(raw || "")
    .trim()
    .replace(/\$/g, "")
    .replace(/,/g, "");
  if (!cleaned) throw new Error("Enter an amount.");
  const value = Number(cleaned);
  if (!Number.isFinite(value) || value < 0) throw new Error("Enter a valid amount.");
  return round2(value);
}

export function parseQuantity(raw) {
  const cleaned = String(raw || "").trim();
  if (!cleaned) return 1;
  const value = Number(cleaned);
  if (!Number.isFinite(value) || value <= 0) throw new Error("Quantity must be more than zero.");
  return value;
}

export function formatMoney(amount) {
  const n = Number(amount) || 0;
  return `$${n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatInvoiceNumber(number) {
  return String(Math.max(1, parseInt(number, 10) || 0)).padStart(8, "0");
}

export function parseInvoiceNumberInput(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (!digits) throw new Error("Enter an invoice number.");
  const number = parseInt(digits, 10);
  if (number < 1) throw new Error("Invoice number must be at least 1.");
  return number;
}

export function invoiceBusinessName(inv) {
  return inv.business_name || inv.business || "";
}

export function suggestedInvoiceNumber(businessName, businessProfile, invoices) {
  const counter = parseInt(businessProfile?.invoice_counter, 10) || 1;
  const matching = Object.values(invoices || {})
    .filter((inv) => !inv.deleted_at && invoiceBusinessName(inv) === businessName)
    .map((inv) => parseInt(inv.invoice_number, 10) || 0);
  if (!matching.length) return counter;
  return Math.max(counter, Math.max(...matching) + 1);
}

export function formatAbn(abn) {
  const digits = String(abn || "").replace(/\D/g, "");
  if (digits.length === 11) {
    return `${digits.slice(0, 2)} ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  }
  return abn || "";
}

export function formatBsb(bsb) {
  const digits = String(bsb || "").replace(/\D/g, "");
  if (digits.length === 6) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return bsb || "";
}

export function formatAccount(acc) {
  const digits = String(acc || "").replace(/\D/g, "");
  if (digits.length === 6) return `${digits.slice(0, 3)} ${digits.slice(3)}`;
  return acc || "";
}

export function formatInvoiceDate(isoDate) {
  if (!isoDate) return "";
  const d = new Date(isoDate + "T12:00:00");
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
}

export function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export function moneyStr(n) {
  return round2(n).toFixed(2);
}
