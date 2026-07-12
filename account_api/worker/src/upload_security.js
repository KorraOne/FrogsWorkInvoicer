const PDF_MAGIC = "%PDF-";
const MAX_PDF_BYTES = 10 * 1024 * 1024;
const MAX_MIGRATE_BYTES = 5 * 1024 * 1024;
const MAX_SYNC_MUTATIONS = 100;
const ALLOWED_MUTATIONS = new Set([
  "upsert_business",
  "upsert_customer",
  "delete_customer",
  "create_invoice",
  "update_invoice_status",
  "delete_invoice",
  "upsert_settings",
  "enqueue_email_send",
]);

export function isPdfBytes(bytes) {
  if (!bytes || bytes.byteLength < 5) return false;
  const head = new TextDecoder().decode(bytes.slice(0, 5));
  return head === PDF_MAGIC;
}

export function decodePdfB64(b64) {
  if (!b64 || typeof b64 !== "string") {
    throw new Error("Invalid PDF payload.");
  }
  const binary = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  if (binary.byteLength > MAX_PDF_BYTES) {
    throw new Error("PDF exceeds 10 MB limit.");
  }
  if (!isPdfBytes(binary)) {
    throw new Error("Uploaded file is not a valid PDF.");
  }
  return binary;
}

export async function readJsonLimited(request, maxBytes) {
  const text = await request.text();
  if (text.length > maxBytes) {
    throw new Error("Request body too large.");
  }
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return {};
  }
}

export function validateSyncMutations(mutations) {
  if (!Array.isArray(mutations)) {
    throw new Error("mutations must be an array.");
  }
  if (mutations.length > MAX_SYNC_MUTATIONS) {
    throw new Error("Too many mutations in one request.");
  }
  for (const mutation of mutations) {
    if (!mutation || !ALLOWED_MUTATIONS.has(mutation.type)) {
      throw new Error(`Invalid mutation type: ${mutation?.type}`);
    }
  }
}

export { MAX_MIGRATE_BYTES };
