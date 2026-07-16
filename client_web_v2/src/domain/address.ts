export const AU_STATES = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];

export function digitsOnly(raw: string): string {
  return String(raw || "").replace(/\D/g, "");
}

export function normalizeAbn(raw: string): string {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length !== 11) throw new Error("ABN must be 11 digits.");
  return digits;
}

export function normalizeBsb(raw: string): string {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length !== 6) throw new Error("BSB must be 6 digits.");
  return `${digits.slice(0, 3)}-${digits.slice(3)}`;
}

export function normalizeAccountNumber(raw: string): string {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length < 5 || digits.length > 9) throw new Error("Account number must be 5–9 digits.");
  return digits;
}

export function formatAddressLines(addr: Record<string, unknown> = {}): string[] {
  const lines: string[] = [];
  if (addr.address_line1) lines.push(String(addr.address_line1));
  if (addr.address_line2) lines.push(String(addr.address_line2));
  const city = [addr.suburb, addr.state, addr.postcode].filter(Boolean).join(" ");
  if (city) lines.push(city);
  return lines;
}

export function formatAddressMultiline(addr: Record<string, unknown>): string {
  return formatAddressLines(addr).join("\n");
}

export function addressSnippet(addr: Record<string, unknown>): string {
  return [addr.suburb, addr.state].filter(Boolean).join(" ") || "";
}

export function normalizeAuAddress(fields: Record<string, string>) {
  const address_line1 = compact(fields.line1);
  const address_line2 = compact(fields.line2);
  const suburb = compact(fields.suburb);
  const state = fields.state ? normalizeState(fields.state) : "";
  const postcode = fields.postcode ? normalizePostcode(fields.postcode) : "";
  if ([address_line2, suburb, state, postcode].some(Boolean) && !address_line1) {
    throw new Error("Address line 1 is required.");
  }
  if (state && !postcode) throw new Error("Postcode is required when a state is selected.");
  if (postcode && !state) throw new Error("State is required when a postcode is entered.");
  return { address_line1, address_line2, suburb, state, postcode };
}

function compact(raw: string): string {
  return String(raw || "").trim().replace(/\s+/g, " ");
}

function normalizeState(raw: string): string {
  const state = String(raw || "").trim().toUpperCase();
  if (!state) return "";
  if (!AU_STATES.includes(state)) throw new Error("State must be one of: ACT, NSW, NT, QLD, SA, TAS, VIC, WA.");
  return state;
}

function normalizePostcode(raw: string): string {
  const pc = String(raw || "").replace(/\D/g, "");
  if (!pc) return "";
  if (pc.length !== 4) throw new Error("Postcode must be 4 digits.");
  return pc;
}

export function addressFieldsHtml(prefix: string, record: Record<string, unknown> = {}): string {
  const p = prefix ? `${prefix}_` : "";
  const opts = AU_STATES.map(
    (s) => `<option value="${s}" ${record.state === s ? "selected" : ""}>${s}</option>`
  ).join("");
  return `
    <div class="field"><label>Address line 1</label><input name="${p}line1" value="${esc(record.address_line1)}"></div>
    <div class="field"><label>Address line 2</label><input name="${p}line2" value="${esc(record.address_line2)}"></div>
    <div class="field-row">
      <div class="field"><label>Suburb</label><input name="${p}suburb" value="${esc(record.suburb)}"></div>
      <div class="field field-narrow"><label>State</label><select name="${p}state"><option value=""></option>${opts}</select></div>
      <div class="field field-narrow"><label>Postcode</label><input name="${p}postcode" inputmode="numeric" value="${esc(record.postcode)}"></div>
    </div>`;
}

export function readAddressFromForm(fd: FormData, prefix = ""): Record<string, string> {
  const p = prefix ? `${prefix}_` : "";
  return {
    line1: String(fd.get(`${p}line1`) || ""),
    line2: String(fd.get(`${p}line2`) || ""),
    suburb: String(fd.get(`${p}suburb`) || ""),
    state: String(fd.get(`${p}state`) || ""),
    postcode: String(fd.get(`${p}postcode`) || ""),
  };
}

function esc(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}
