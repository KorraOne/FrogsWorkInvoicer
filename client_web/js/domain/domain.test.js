import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyRegistrationToParsedItems, parseLineItems } from "./gst.js";
import { computeDueDate, normalizeDueNetDays } from "./due_dates.js";
import { dashboardTotals } from "./invoices_group.js";
import { normalizeAbn } from "./address.js";
import { suggestedInvoiceNumber } from "./invoice_format.js";

describe("gst", () => {
  it("applies 10% GST to taxable lines", () => {
    const rows = [{ description: "Work", amount: "100", qty: "1", gst_free: false }];
    const result = parseLineItems(rows, true);
    assert.equal(result.gstAmount, 10);
    assert.equal(result.totalIncGst, 110);
  });

  it("strips GST when not registered", () => {
    const rows = [{ description: "Work", amount: "100", qty: "1", gst_free: false }];
    const result = parseLineItems(rows, false);
    assert.equal(result.gstAmount, 0);
    assert.equal(result.totalIncGst, 100);
  });
});

describe("due_dates", () => {
  it("normalizes net days", () => {
    assert.equal(normalizeDueNetDays("14"), 14);
    assert.equal(normalizeDueNetDays("0"), 14);
  });

  it("computes net days due date", () => {
    const due = computeDueDate("2026-07-01", "net_days", 14);
    assert.equal(due.toISOString().slice(0, 10), "2026-07-15");
  });
});

describe("dashboard", () => {
  it("sums month totals", () => {
    const invoices = {
      "00000001": {
        invoice_number: 1,
        invoice_date: "2026-07-05",
        status: "sent",
        total_inc_gst: "110",
        amount_ex_gst: "100",
      },
    };
    const totals = dashboardTotals(invoices, new Date("2026-07-12"));
    assert.equal(totals.month.count, 1);
    assert.equal(totals.month.inc_gst, 110);
    assert.equal(totals.outstanding.count, 1);
  });
});

describe("address", () => {
  it("validates ABN length", () => {
    assert.throws(() => normalizeAbn("123"));
  });
});

describe("invoice_format", () => {
  it("suggests next invoice number", () => {
    const n = suggestedInvoiceNumber("Biz", { invoice_counter: 5 }, {
      "00000003": { invoice_number: 3, business_name: "Biz" },
    });
    assert.equal(n, 5);
  });
});
