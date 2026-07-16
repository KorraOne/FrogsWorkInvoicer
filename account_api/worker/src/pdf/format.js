export function formatMoney(amount) {
  const n = Number(amount);
  const v = Number.isFinite(n) ? n : 0;
  return `$${v.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatInvoiceNumber(number) {
  return String(parseInt(number, 10) || 0).padStart(8, "0");
}

export function formatAbn(abn) {
  const digits = String(abn || "").replace(/\D/g, "");
  if (digits.length === 11) {
    return `${digits.slice(0, 2)} ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8, 11)}`;
  }
  return String(abn || "");
}

export function formatBsb(bsb) {
  const digits = String(bsb || "").replace(/\D/g, "");
  if (digits.length === 6) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return String(bsb || "");
}

export function formatAccount(acc) {
  const digits = String(acc || "").replace(/\D/g, "");
  return digits || String(acc || "");
}

export function formatDisplayDate(iso) {
  if (!iso) return "";
  const d = new Date(String(iso).slice(0, 10) + "T12:00:00");
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
}

export function formatAddressMultiline(addr = {}) {
  const lines = [];
  if (addr.address_line1) lines.push(String(addr.address_line1));
  if (addr.address_line2) lines.push(String(addr.address_line2));
  const city = [addr.suburb, addr.state, addr.postcode].filter(Boolean).join(" ");
  if (city) lines.push(city);
  return lines;
}

export function formatQty(qty) {
  const n = Number(qty);
  if (!Number.isFinite(n)) return "1";
  return Number.isInteger(n) ? String(n) : String(n);
}
