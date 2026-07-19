import { router } from "../router";

type ApplyFilter = (q: string) => void;

let applyInvoiceFilter: ApplyFilter | null = null;
let applyQuoteFilter: ApplyFilter | null = null;

/** Called once from invoices screen module init / first render. */
export function registerInvoiceListFilter(apply: ApplyFilter) {
  applyInvoiceFilter = apply;
}

/** Called once from quotes screen module init / first render. */
export function registerQuoteListFilter(apply: ApplyFilter) {
  applyQuoteFilter = apply;
}

export function openInvoicesFiltered(q: string) {
  applyInvoiceFilter?.(String(q || "").trim());
  router.navigate("invoices");
}

export function openQuotesFiltered(q: string) {
  applyQuoteFilter?.(String(q || "").trim());
  router.navigate("quotes");
}
