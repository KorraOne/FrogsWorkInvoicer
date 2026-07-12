import { cache } from "../idb.js";
import { upsertCustomer, deleteCustomer, flushQueue } from "../sync.js";
import { normalizeAuAddress, normalizeAbn } from "../domain/address.js";
import { addressFields, readAddressFromForm } from "../components/forms.js";
import { router } from "../router.js";

export async function renderCustomers(panel, ctx) {
  if (router.sub === "add" || router.sub === "edit") {
    return renderCustomerForm(panel, ctx);
  }
  const customers = await cache.getCustomers();
  const names = Object.keys(customers).sort();
  panel.innerHTML = `
    <div class="panel-header"><h2>Customers</h2>
      <button type="button" class="btn small primary" id="add-customer">Add customer</button></div>
    ${names.length ? names.map((n) => customerCard(n, customers[n])).join("") : '<p class="hint">No customers yet.</p>'}`;
  panel.querySelector("#add-customer")?.addEventListener("click", () => router.navigate("customers", "add"));
  panel.querySelectorAll("[data-edit-customer]").forEach((btn) => {
    btn.addEventListener("click", () => router.navigate("customers", "edit", { name: btn.dataset.editCustomer }));
  });
}

function customerCard(name, record) {
  const addr = [record.address_line1, record.suburb, record.state].filter(Boolean).join(", ");
  return `<article class="card card-click" data-edit-customer="${esc(name)}">
    <strong>${esc(name)}</strong>
    <div class="meta">${esc(record.email || "No email")}${addr ? ` · ${esc(addr)}` : ""}</div>
  </article>`;
}

async function renderCustomerForm(panel, ctx) {
  const editing = router.sub === "edit";
  const name = editing ? router.params.name || router.params.id : "";
  const customers = await cache.getCustomers();
  const record = editing ? customers[name] || {} : {};
  panel.innerHTML = `
    <form id="customer-form" class="panel">
      <h2>${editing ? "Edit customer" : "Add customer"}</h2>
      ${editing ? `<div class="field"><label>Customer name</label><input value="${esc(name)}" disabled></div>` : `<div class="field"><label>Customer name</label><input name="name" required></div>`}
      <div class="field"><label>Email</label><input name="email" type="email" value="${esc(record.email || "")}"></div>
      ${addressFields("", record)}
      <div class="field"><label>ABN (optional)</label><input name="abn" value="${esc(record.abn || "")}" inputmode="numeric"></div>
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="submit" class="btn primary">Save</button>
        ${editing ? `<button type="button" class="btn danger" id="delete-customer">Delete</button>` : ""}
        <button type="button" class="btn secondary" id="cancel-customer">Cancel</button>
      </div>
    </form>`;
  document.getElementById("cancel-customer").addEventListener("click", () => router.navigate("customers"));
  document.getElementById("customer-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("form-error");
    err.hidden = true;
    try {
      const fd = new FormData(e.target);
      const custName = editing ? name : (fd.get("name") || "").trim();
      if (!custName) throw new Error("Customer name is required.");
      const addr = normalizeAuAddress(readAddressFromForm(fd));
      const abn = fd.get("abn") ? normalizeAbn(fd.get("abn")) : "";
      const payload = { email: (fd.get("email") || "").trim(), ...addr, abn };
      await upsertCustomer(custName, payload);
      await flushQueue(ctx.onSyncStatus);
      router.navigate("customers");
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
  if (editing) {
    document.getElementById("delete-customer")?.addEventListener("click", async () => {
      if (!confirm(`Delete customer "${name}"?`)) return;
      const invoices = await cache.getInvoices();
      const inUse = Object.values(invoices).some((inv) => !inv.deleted_at && inv.customer_name === name);
      if (inUse) {
        alert("Cannot delete — customer is used on an invoice.");
        return;
      }
      await deleteCustomer(name);
      await flushQueue(ctx.onSyncStatus);
      router.navigate("customers");
    });
  }
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}
