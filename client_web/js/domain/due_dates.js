export const VALID_DUE_RULE_TYPES = ["net_days", "end_next_week", "end_next_month", "fixed_date"];
export const DEFAULT_DUE_RULE_TYPE = "net_days";
export const DEFAULT_DUE_NET_DAYS = 14;

export function normalizeDueRuleType(value) {
  return VALID_DUE_RULE_TYPES.includes(value) ? value : DEFAULT_DUE_RULE_TYPE;
}

export function normalizeDueNetDays(value, defaultDays = DEFAULT_DUE_NET_DAYS) {
  const days = parseInt(value, 10);
  return days >= 1 ? days : defaultDays;
}

function parseIsoDate(value) {
  if (!value) return null;
  const d = new Date(String(value).slice(0, 10) + "T12:00:00");
  return Number.isNaN(d.getTime()) ? null : d;
}

function lastDayOfMonth(year, month) {
  return new Date(year, month + 1, 0);
}

function endOfWeekSunday(d) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + (6 - copy.getDay()));
  return copy;
}

export function computeDueDate(invoiceDate, ruleType, netDays = DEFAULT_DUE_NET_DAYS, fixedDate = null) {
  const base = parseIsoDate(invoiceDate) || new Date();
  const rule = normalizeDueRuleType(ruleType);
  if (rule === "fixed_date") {
    let due = parseIsoDate(fixedDate) || addDays(base, normalizeDueNetDays(netDays));
    if (due < base) due = base;
    return due;
  }
  if (rule === "net_days") return addDays(base, normalizeDueNetDays(netDays));
  if (rule === "end_next_week") return addDays(endOfWeekSunday(base), 7);
  if (rule === "end_next_month") {
    const y = base.getFullYear();
    const m = base.getMonth();
    if (m === 11) return lastDayOfMonth(y + 1, 0);
    return lastDayOfMonth(y, m + 1);
  }
  return addDays(base, DEFAULT_DUE_NET_DAYS);
}

function addDays(d, days) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function formatDueDate(d) {
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
}

export function dueRuleLabel(ruleType, netDays = DEFAULT_DUE_NET_DAYS, fixedDate = null) {
  const rule = normalizeDueRuleType(ruleType);
  if (rule === "net_days") {
    const days = normalizeDueNetDays(netDays);
    return `Net ${days} day${days === 1 ? "" : "s"}`;
  }
  if (rule === "end_next_week") return "End of next week";
  if (rule === "end_next_month") return "End of next month";
  const due = parseIsoDate(fixedDate);
  return due ? formatDueDate(due) : "Specific date";
}

export function dueRuleFromSettings(settings = {}) {
  let ruleType = normalizeDueRuleType(settings.due_rule_type);
  if (ruleType === "fixed_date") ruleType = DEFAULT_DUE_RULE_TYPE;
  return {
    due_rule_type: ruleType,
    due_net_days: normalizeDueNetDays(settings.due_net_days),
    due_fixed_date: "",
  };
}

export function duePrefsForNewInvoice(settings = {}, invoiceDate = null) {
  const base = parseIsoDate(invoiceDate) || new Date();
  const last = {
    due_rule_type: (settings.last_due_rule_type || "").trim(),
    due_net_days: settings.last_due_net_days,
    due_fixed_date: settings.last_due_fixed_date || "",
  };
  if (last.due_rule_type) {
    const prefs = {
      due_rule_type: normalizeDueRuleType(last.due_rule_type),
      due_net_days: normalizeDueNetDays(last.due_net_days),
      due_fixed_date: last.due_fixed_date,
    };
    if (duePrefsStillValid(prefs, base)) return prefs;
  }
  return dueRuleFromSettings(settings);
}

function duePrefsStillValid(prefs, invoiceDate) {
  if (prefs.due_rule_type !== "fixed_date") return true;
  const fixed = parseIsoDate(prefs.due_fixed_date);
  return Boolean(fixed && fixed >= invoiceDate);
}

export function dueRuleFromFormData(form, settings = {}) {
  const defaults = duePrefsForNewInvoice(settings);
  const ruleType = normalizeDueRuleType(form.due_rule_type || defaults.due_rule_type);
  const netDays = normalizeDueNetDays(form.due_net_days, defaults.due_net_days);
  const fixed = form.due_fixed_date || defaults.due_fixed_date || "";
  const due = computeDueDate(new Date().toISOString().slice(0, 10), ruleType, netDays, fixed);
  return {
    due_rule_type: ruleType,
    due_net_days: netDays,
    due_fixed_date: ruleType === "fixed_date" ? due.toISOString().slice(0, 10) : "",
  };
}

export function invoiceDueSummary(invoiceDate, ruleType, netDays, fixedDate = null) {
  const rule = normalizeDueRuleType(ruleType);
  const days = normalizeDueNetDays(netDays);
  const due = computeDueDate(invoiceDate, rule, days, fixedDate);
  return {
    due_rule_type: rule,
    due_net_days: days,
    due_fixed_date: rule === "fixed_date" ? due.toISOString().slice(0, 10) : null,
    due_rule_label: dueRuleLabel(rule, days, fixedDate),
    due_date_iso: due.toISOString().slice(0, 10),
    due_date_fmt: formatDueDate(due),
  };
}

export function resolveInvoiceDueDate(invoice, settings = {}) {
  const due = parseIsoDate(invoice.due_date);
  if (due) return due;
  const invoiceDate = parseIsoDate(invoice.invoice_date);
  if (!invoiceDate) return null;
  const ruleType = invoice.due_rule_type || settings.due_rule_type;
  const netDays = invoice.due_rule_type ? invoice.due_net_days : settings.due_net_days;
  const fixedDate = invoice.due_fixed_date || settings.due_fixed_date;
  return computeDueDate(invoice.invoice_date, ruleType, netDays, fixedDate);
}

export function dueCountdownForInvoice(invoice, today = null, settings = {}) {
  const due = resolveInvoiceDueDate(invoice, settings);
  if (!due) return null;
  const now = today || new Date();
  const todayDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dueDate = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  const delta = Math.round((dueDate - todayDate) / 86400000);
  const due_date_fmt = formatDueDate(due);
  if (delta > 0) {
    return { kind: "due_soon", days: delta, label: `Due in ${delta} day${delta === 1 ? "" : "s"}`, due_date_fmt };
  }
  if (delta === 0) return { kind: "due_today", days: 0, label: "Due today", due_date_fmt };
  const overdue = Math.abs(delta);
  return {
    kind: "overdue",
    days: overdue,
    label: `Overdue by ${overdue} day${overdue === 1 ? "" : "s"}`,
    due_date_fmt,
  };
}

export function sentInvoiceSortKey(invoice, settings = {}) {
  const due = resolveInvoiceDueDate(invoice, settings);
  const num = parseInt(invoice.invoice_number, 10) || 0;
  if (!due) return [1, "9999-99-99", num];
  return [0, due.toISOString().slice(0, 10), num];
}
