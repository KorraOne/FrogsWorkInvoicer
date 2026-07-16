import { renderClassicInvoice } from "./pdf/templates/classic.js";

/**
 * @param {object} invoice
 * @param {object} [business]
 * @param {object} [customer]
 * @param {{ templateId?: string }} [opts]
 */
export async function buildInvoicePdf(invoice, business = {}, customer = {}, opts = {}) {
  const templateId = opts.templateId || business.pdf_template || invoice.pdf_template || "classic";
  if (templateId === "classic") {
    return renderClassicInvoice(invoice, business, customer);
  }
  throw new Error(`Unknown PDF template: ${templateId}`);
}

export {
  HEADER_SLOT_FRACTION,
  HEADER_CANVAS_WIDTH,
  HEADER_CANVAS_HEIGHT,
  CONTENT_WIDTH,
  PAGE_MARGIN,
} from "./pdf/geometry.js";
