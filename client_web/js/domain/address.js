export const AU_STATES = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];

function compactLine(raw) {
  return String(raw || "")
    .trim()
    .replace(/\s+/g, " ");
}

function compactSuburb(raw) {
  const text = compactLine(raw);
  if (!text) return "";
  return text.replace(/\b\w/g, (c) => c.toUpperCase());
}

export function normalizeState(raw) {
  const state = String(raw || "")
    .trim()
    .toUpperCase();
  if (!state) return "";
  if (!AU_STATES.includes(state)) {
    throw new Error("State must be one of: ACT, NSW, NT, QLD, SA, TAS, VIC, WA.");
  }
  return state;
}

export function normalizePostcode(raw) {
  const pc = String(raw || "").replace(/\D/g, "");
  if (!pc) return "";
  if (pc.length !== 4) throw new Error("Postcode must be 4 digits.");
  return pc;
}

export function normalizeAuAddress({ line1, line2, suburb, state, postcode }) {
  const address_line1 = compactLine(line1);
  const address_line2 = compactLine(line2);
  const suburb_s = compactSuburb(suburb);
  const state_s = state ? normalizeState(state) : "";
  const postcode_s = postcode ? normalizePostcode(postcode) : "";

  if ([address_line2, suburb_s, state_s, postcode_s].some(Boolean) && !address_line1) {
    throw new Error("Address line 1 is required.");
  }
  if (state_s && !postcode_s) throw new Error("Postcode is required when a state is selected.");
  if (postcode_s && !state_s) throw new Error("State is required when a postcode is entered.");

  return {
    address_line1,
    address_line2: address_line2,
    suburb: suburb_s,
    state: state_s,
    postcode: postcode_s,
  };
}

export function formatAddressLines(addr = {}) {
  const lines = [];
  if (addr.address_line1) lines.push(addr.address_line1);
  if (addr.address_line2) lines.push(addr.address_line2);
  const city = [addr.suburb, addr.state, addr.postcode].filter(Boolean).join(" ");
  if (city) lines.push(city);
  return lines;
}

export function formatAddressMultiline(addr) {
  return formatAddressLines(addr).join("\n");
}

export function digitsOnly(raw) {
  return String(raw || "").replace(/\D/g, "");
}

export function normalizeAbn(raw) {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length !== 11) throw new Error("ABN must be 11 digits.");
  return digits;
}

export function normalizeBsb(raw) {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length !== 6) throw new Error("BSB must be 6 digits.");
  return `${digits.slice(0, 3)}-${digits.slice(3)}`;
}

export function normalizeAccountNumber(raw) {
  const digits = digitsOnly(raw);
  if (!digits) return "";
  if (digits.length < 5 || digits.length > 9) throw new Error("Account number must be 5–9 digits.");
  return digits;
}
