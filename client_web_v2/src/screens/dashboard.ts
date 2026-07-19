import { cache } from "../data/idb";
import { isSetupBusinessComplete } from "../domain/businessCompleteness";
import { dashboardTotals } from "../domain/invoicesGroup";
import { formatMoney } from "../domain/invoiceFormat";
import { isGstRegistered } from "../domain/gst";
import { router } from "../router";
import type { AppContext } from "../types";

export async function renderDashboard(panel: HTMLElement, _ctx: AppContext) {
  const [invoices, businesses, settings] = await Promise.all([
    cache.getInvoices(),
    cache.getBusinesses(),
    cache.getSettings(),
  ]);
  const totals = dashboardTotals(invoices);
  const defaultBizName = String(settings.default_business || Object.keys(businesses)[0] || "");
  const defaultBiz: Record<string, unknown> = businesses[defaultBizName] || {};
  const showExGst = isGstRegistered(defaultBiz);
  const businessIncomplete = !isSetupBusinessComplete(businesses, settings);

  const bannerHtml = businessIncomplete
    ? `<div class="setup-notice" role="status">
        <p class="setup-notice-title">Your business details aren't filled in</p>
        <p class="hint">Add your name, email, address, and payment details so they appear on invoices.</p>
        <button type="button" class="btn secondary" id="go-business-setup">Add business details</button>
      </div>`
    : "";

  panel.innerHTML = `
    ${bannerHtml}
    <section class="panel">
      <h2>Sales invoice totals</h2>
      <div class="preview-section">
        <div class="preview-row">
          <span class="preview-label">Sales this month</span>
          <span class="amount-stack">
            <strong>${formatMoney(totals.month.inc_gst)}</strong>
            ${showExGst ? `<small>ex GST ${formatMoney(totals.month.ex_gst)}</small>` : ""}
          </span>
        </div>
        <div class="preview-row">
          <span class="preview-label">Outstanding (${totals.outstanding.count})</span>
          <strong>${formatMoney(totals.outstanding.inc_gst)}</strong>
        </div>
        <div class="preview-row">
          <span class="preview-label">Paid all time</span>
          <strong>${formatMoney(totals.paid.inc_gst)}</strong>
        </div>
      </div>
    </section>
    <div class="btn-row stacked">
      <button type="button" class="btn primary" id="go-create">Create sales invoice</button>
      <button type="button" class="btn ghost" id="go-invoices">Past invoices →</button>
    </div>`;

  panel.querySelector("#go-business-setup")?.addEventListener("click", () =>
    router.navigate("settings", "business")
  );
  panel.querySelector("#go-create")?.addEventListener("click", () =>
    router.navigate("invoices", "create")
  );
  panel.querySelector("#go-invoices")?.addEventListener("click", () => router.navigate("invoices"));
}
