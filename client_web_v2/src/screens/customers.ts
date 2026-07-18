import { confirmSheet, emptyStateHtml, showToast } from "../components/ui";
import { cache } from "../data/idb";
import { deleteCustomer, flushQueue, upsertCustomer } from "../data/sync";
import {
  addressFieldsHtml,
  addressSnippet,
  normalizeAbn,
  normalizeAuAddress,
  readAddressFromForm,
} from "../domain/address";
import { esc } from "../lib/escape";
import { attachUnsavedGuard, clearLeaveGuard } from "../lib/unsaved";
import { router } from "../router";
import type { AppContext } from "../types";

export async function renderCustomers(panel: HTMLElement, ctx: AppContext) {
  clearLeaveGuard();
  if (router.sub === "add" || router.sub === "edit") {
    return renderCustomerForm(panel, ctx);
  }
  const customers = await cache.getCustomers();
  const names = Object.keys(customers).sort();
  panel.innerHTML = `
    <div class="panel-header"><h2>Customers</h2><button type="button" class="btn small primary" id="add-customer">Add</button></div>
    ${
      names.length
        ? names.map((n) => customerCard(n, customers[n])).join("")
        : emptyStateHtml(
            "No customers yet",
            "Add a customer before creating an invoice.",
            "empty-add-customer",
            "Add customer"
          )
    }`;
  panel.querySelector("#add-customer")?.addEventListener("click", () =>
    router.navigate("customers", "add")
  );
  panel.querySelector("#empty-add-customer")?.addEventListener("click", () =>
    router.navigate("customers", "add")
  );
  panel.querySelectorAll("[data-edit-customer]").forEach((btn) => {
    btn.addEventListener("click", () =>
      router.navigate("customers", "edit", {
        name: (btn as HTMLElement).dataset.editCustomer || "",
      })
    );
  });
}

function customerCard(name: string, record: Record<string, unknown>) {
  const snippet = addressSnippet(record);
  const notes = String(record.notes || "").trim();
  const notesHint =
    notes.length > 80 ? `${notes.slice(0, 80).trim()}…` : notes;
  return `<article class="card card-click" data-edit-customer="${esc(name)}">
    <strong>${esc(name)}</strong>
    <div class="meta">${esc(String(record.email || "No email"))}</div>
    ${snippet ? `<div class="meta">${esc(snippet)}</div>` : ""}
    ${notesHint ? `<div class="meta meta-notes">${esc(notesHint)}</div>` : ""}
  </article>`;
}

async function renderCustomerForm(panel: HTMLElement, ctx: AppContext) {
  const editing = router.sub === "edit";
  const name = editing ? router.params.name || "" : "";
  const customers = await cache.getCustomers();
  const record = editing ? customers[name] || {} : {};
  panel.innerHTML = `
    <form id="customer-form" class="panel" novalidate>
      <h2>${editing ? "Edit customer" : "Add customer"}</h2>
      ${
        editing
          ? `<div class="field"><label>Name</label><input value="${esc(name)}" disabled></div>`
          : `<div class="field"><label>Name</label><input name="name" required></div>`
      }
      <div class="field"><label>Email</label><input name="email" type="email" value="${esc(record.email)}"></div>
      ${addressFieldsHtml("", record)}
      <div class="field"><label>ABN (optional)</label><input name="abn" value="${esc(record.abn)}"></div>
      <div class="field"><label>Notes (to yourself)</label>
        <textarea name="notes" rows="2" placeholder="Not shown on invoices">${esc(record.notes || "")}</textarea></div>
      <p class="error-text" id="form-error" hidden></p>
      <div class="btn-row">
        <button type="button" class="btn primary" id="save-customer">Save</button>
        ${editing ? `<button type="button" class="btn danger" id="delete-customer">Delete</button>` : ""}
        <button type="button" class="btn secondary" id="cancel-customer">Cancel</button>
      </div>
    </form>`;

  const form = panel.querySelector("#customer-form") as HTMLFormElement;
  const guard = attachUnsavedGuard(form);

  panel.querySelector("#cancel-customer")?.addEventListener("click", () =>
    guard.attemptLeave(() => router.navigate("customers"))
  );
  panel.querySelector("#save-customer")?.addEventListener("click", async () => {
    const err = panel.querySelector("#form-error") as HTMLElement;
    err.hidden = true;
    try {
      const fd = new FormData(form);
      const custName = editing ? name : String(fd.get("name") || "").trim();
      if (!custName) throw new Error("Customer name is required.");
      const email = String(fd.get("email") || "").trim();
      const addr = normalizeAuAddress(readAddressFromForm(fd));
      const abn = fd.get("abn") ? normalizeAbn(String(fd.get("abn"))) : "";
      const notes = String(fd.get("notes") || "").trim();
      const existing = editing
        ? (await cache.getCustomers())[custName]
        : null;
      const createdVia =
        (existing && typeof existing.created_via === "string" && existing.created_via) ||
        (editing ? undefined : "list");
      await upsertCustomer(custName, {
        email,
        ...addr,
        abn,
        notes,
        ...(createdVia ? { created_via: createdVia } : {}),
      });
      await flushQueue(ctx.onSyncStatus);
      guard.clear();
      showToast("Customer saved.", "success");
      router.navigate("customers");
    } catch (ex) {
      err.textContent = ex instanceof Error ? ex.message : "Save failed.";
      err.hidden = false;
    }
  });

  if (editing) {
    panel.querySelector("#delete-customer")?.addEventListener("click", async () => {
      const invoices = await cache.getInvoices();
      const inUse = Object.values(invoices).some(
        (inv) => !inv.deleted_at && inv.customer_name === name
      );
      if (inUse) {
        showToast("Cannot delete — customer is used on an invoice.", "error");
        return;
      }
      const ok = await confirmSheet(`Delete customer "${name}"?`, "Delete");
      if (!ok) return;
      guard.clear();
      await deleteCustomer(name);
      await flushQueue(ctx.onSyncStatus);
      showToast("Customer deleted.", "success");
      router.navigate("customers");
    });
  }
}
