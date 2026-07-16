/** Classic PDF / logo header geometry — keep in sync with client_web_v2 domain/invoiceHeader.ts */
export const PAGE_WIDTH = 595.28;
export const PAGE_HEIGHT = 841.89;
export const PAGE_MARGIN = 56.69; // ~20mm
export const CONTENT_WIDTH = PAGE_WIDTH - 2 * PAGE_MARGIN;
export const HEADER_SLOT_FRACTION = 0.6;
export const HEADER_CANVAS_WIDTH = 900;
export const HEADER_CANVAS_HEIGHT = 500;
export const ACCENT = { r: 0.173, g: 0.243, b: 0.314 }; // #2c3e50
export const LIGHT_GREY = { r: 0.957, g: 0.957, b: 0.957 };
export const BORDER_GREY = { r: 0.8, g: 0.8, b: 0.8 };
export const TEXT = { r: 0.12, g: 0.16, b: 0.22 };
export const MUTED = { r: 0.4, g: 0.4, b: 0.4 };
