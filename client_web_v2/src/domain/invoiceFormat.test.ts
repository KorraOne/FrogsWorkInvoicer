import { describe, expect, it } from "vitest";
import { formatMoney, round2 } from "./invoiceFormat";

describe("invoiceFormat", () => {
  it("rounds to two decimals", () => {
    expect(round2(1.005)).toBe(1.01);
  });

  it("formats AUD money", () => {
    expect(formatMoney(1234.5)).toContain("1,234.50");
  });
});
