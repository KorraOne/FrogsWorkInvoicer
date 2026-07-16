import { api } from "../api.js";
import { cache } from "../idb.js";
import { pullBootstrap, flushQueue } from "../sync.js";
import { dashboardTotals } from "../domain/invoices_group.js";
import { dashboardAmounts, businessGstRegistered, resolveActiveBusiness } from "../domain/dashboard.js";
import { router } from "../router.js";

export async function renderDashboard(panel, { entitlements }) {
  const [invoices, businesses, settings] = await Promise.all([
    cache.getInvoices(),
    cache.getBusinesses(),
    cache.getSettings(),
  ]);
  const totals = dashboardTotals(invoices);
  const gstReg = businessGstRegistered(businesses, settings);
  const month = dashboardAmounts(totals.month, gstReg);
  const outstanding = dashboardAmounts(totals.outstanding, gstReg);
  const paid = dashboardAmounts(totals.paid, gstReg);

  let accountHtml = "";
  if (entitlements) {
    accountHtml = `
      <div class="preview-row"><span class="preview-label">Subscription</span>
        <span>${entitlements.active ? "Active" : "Inactive"}</span></div>`;
  }

  panel.innerHTML = `
    <section class="panel">
      <h2>Sales invoice totals</h2>
      <div class="preview-section">
        <div class="preview-row">
          <span class="preview-label">Sales invoiced this month</span>
          <span class="amount-stack"><strong>${month.primary}</strong>${month.secondary ? `<small>${month.secondary}</small>` : ""}</span>
        </div>
        <div class="preview-row">
          <span class="preview-label">Outstanding (sent, unpaid)</span>
          <span class="amount-stack"><strong>${outstanding.primary}</strong>${outstanding.secondary ? `<small>${outstanding.secondary}</small>` : ""}
            <small class="meta">(${totals.outstanding.count} invoice${totals.outstanding.count === 1 ? "" : "s"})</small></span>
        </div>
        <div class="preview-row">
          <span class="preview-label">Paid (all time in list)</span>
          <span class="amount-stack"><strong>${paid.primary}</strong>${paid.secondary ? `<small>${paid.secondary}</small>` : ""}</span>
        </div>
      </div>
    </section>
    ${accountHtml ? `<section class="panel"><h2>Your account</h2>${accountHtml}</section>` : ""}
    <div class="btn-row">
      <button type="button" class="btn primary nav-card-btn" data-go="create">Create sales invoice</button>
      <button type="button" class="btn secondary nav-card-btn" data-go="invoices">Past invoices</button>
    </div>`;

  panel.querySelector('[data-go="create"]')?.addEventListener("click", () => router.navigate("invoices", "create"));
  panel.querySelector('[data-go="invoices"]')?.addEventListener("click", () => router.navigate("invoices"));
}
