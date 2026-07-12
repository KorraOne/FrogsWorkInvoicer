import { round2 } from "./invoice_format.js";

export function isGstRegistered(settings) {
  return Boolean(settings?.gst_registered);
}

export function parseGstRegisteredForm(value) {
  const v = String(value || "")
    .trim()
    .toLowerCase();
  return v === "yes" || v === "true" || v === "1" || v === "on";
}

export function validateBusinessGstSettings(profile) {
  const abn = String(profile?.business_abn || profile?.abn || "").replace(/\D/g, "");
  if (isGstRegistered(profile) && !abn) {
    return "ABN required when registered for GST.";
  }
  return null;
}

export function parseLineItems(rows, gstRegistered = true) {
  const items = [];
  let rowNum = 0;
  for (const row of rows) {
    const desc = String(row.description || "").trim();
    const amtRaw = String(row.amount || row.unit_amount_ex_gst || "").trim();
    const qtyRaw = String(row.qty ?? row.quantity ?? "").trim();
    if (!desc && !amtRaw && !qtyRaw) continue;
    rowNum += 1;
    if (!desc) throw new Error(`Item ${rowNum}: add a description.`);
    const unit = parseAmountField(amtRaw, rowNum);
    const qty = parseQtyField(qtyRaw, rowNum);
    const lineTotal = round2(qty * unit);
    const gstApplicable = gstRegistered && !row.gst_free;
    items.push({
      description: desc,
      quantity: qty,
      unit_amount_ex_gst: unit,
      amount_ex_gst: lineTotal,
      gst_applicable: gstApplicable,
    });
  }
  if (!items.length) throw new Error("Add at least one line item with a description and amount.");
  const subtotal = round2(items.reduce((s, i) => s + i.amount_ex_gst, 0));
  return applyRegistrationToParsedItems(items, subtotal, gstRegistered);
}

function parseAmountField(raw, rowNum) {
  const cleaned = raw.replace(/\$/g, "").replace(/,/g, "");
  if (!cleaned) throw new Error(`Item ${rowNum}: enter a valid amount.`);
  const value = Number(cleaned);
  if (!Number.isFinite(value) || value < 0) throw new Error(`Item ${rowNum}: enter a valid amount.`);
  return round2(value);
}

function parseQtyField(raw, rowNum) {
  if (!raw) return 1;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Item ${rowNum}: enter a valid quantity.`);
  return value;
}

export function applyRegistrationToParsedItems(items, subtotal, gstRegistered) {
  if (gstRegistered) {
    const taxable = round2(items.filter((i) => i.gst_applicable).reduce((s, i) => s + i.amount_ex_gst, 0));
    const gstFree = round2(items.filter((i) => !i.gst_applicable).reduce((s, i) => s + i.amount_ex_gst, 0));
    const gstAmount = round2(taxable * 0.1);
    const totalIncGst = round2(taxable + gstFree + gstAmount);
    return { items, subtotal, gstAmount, totalIncGst, taxableExGst: taxable, gstFreeExGst: gstFree };
  }
  for (const item of items) item.gst_applicable = false;
  return {
    items,
    subtotal,
    gstAmount: 0,
    totalIncGst: subtotal,
    taxableExGst: 0,
    gstFreeExGst: subtotal,
  };
}

export function lineItemsSummary(invoice) {
  const items = invoice.line_items;
  if (items?.length) {
    return items.map((i) => i.description).filter(Boolean).join("; ");
  }
  return invoice.description || "";
}
