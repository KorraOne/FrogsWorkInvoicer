"""Invoice due date rules — compute concrete due dates from settings or per-invoice choices."""

import calendar
import re
from datetime import date, timedelta

VALID_DUE_RULE_TYPES = ("net_days", "end_next_week", "end_next_month")
DEFAULT_DUE_RULE_TYPE = "net_days"
DEFAULT_DUE_NET_DAYS = 14


def normalize_due_rule_type(value):
    if value in VALID_DUE_RULE_TYPES:
        return value
    return DEFAULT_DUE_RULE_TYPE


def normalize_due_net_days(value, default=DEFAULT_DUE_NET_DAYS):
    try:
        days = int(value)
        if days >= 1:
            return days
    except (TypeError, ValueError):
        pass
    return default


def last_day_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def end_of_week_sunday(d):
    return d + timedelta(days=(6 - d.weekday()))


def compute_due_date(invoice_date, rule_type, net_days=DEFAULT_DUE_NET_DAYS):
    rule_type = normalize_due_rule_type(rule_type)
    if rule_type == "net_days":
        return invoice_date + timedelta(days=normalize_due_net_days(net_days))
    if rule_type == "end_next_week":
        return end_of_week_sunday(invoice_date) + timedelta(days=7)
    if rule_type == "end_next_month":
        year, month = invoice_date.year, invoice_date.month
        if month == 12:
            return last_day_of_month(year + 1, 1)
        return last_day_of_month(year, month + 1)
    return invoice_date + timedelta(days=DEFAULT_DUE_NET_DAYS)


def due_rule_label(rule_type, net_days=DEFAULT_DUE_NET_DAYS):
    rule_type = normalize_due_rule_type(rule_type)
    if rule_type == "net_days":
        days = normalize_due_net_days(net_days)
        suffix = "" if days == 1 else "s"
        return f"Net {days} day{suffix}"
    if rule_type == "end_next_week":
        return "End of next week"
    return "End of next month"


def format_due_date(d):
    return d.strftime("%d %B %Y")


def due_rule_from_settings(settings):
    return {
        "due_rule_type": normalize_due_rule_type(settings.get("due_rule_type")),
        "due_net_days": normalize_due_net_days(settings.get("due_net_days")),
    }


def due_rule_from_form_data(form, settings=None):
    defaults = due_rule_from_settings(settings or {})
    return {
        "due_rule_type": normalize_due_rule_type(
            form.get("due_rule_type") or defaults["due_rule_type"]
        ),
        "due_net_days": normalize_due_net_days(
            form.get("due_net_days"), defaults["due_net_days"]
        ),
    }


def merge_due_rule_into_form(form, settings):
    defaults = due_rule_from_settings(settings)
    form.setdefault("due_rule_type", defaults["due_rule_type"])
    form["due_net_days"] = str(
        normalize_due_net_days(form.get("due_net_days"), defaults["due_net_days"])
    )
    return form


def migrate_settings_due_rule(settings):
    changed = False
    if "due_rule_type" not in settings:
        pt = (settings.get("payment_terms") or "").strip().lower()
        if "next week" in pt:
            settings["due_rule_type"] = "end_next_week"
        elif "next month" in pt or "month end" in pt or "eom" in pt:
            settings["due_rule_type"] = "end_next_month"
        else:
            match = re.search(r"(\d+)", pt)
            settings["due_rule_type"] = "net_days"
            settings["due_net_days"] = int(match.group(1)) if match else DEFAULT_DUE_NET_DAYS
        changed = True
    if "due_net_days" not in settings:
        settings["due_net_days"] = DEFAULT_DUE_NET_DAYS
        changed = True
    return changed


def invoice_due_summary(invoice_date, rule_type, net_days):
    due = compute_due_date(invoice_date, rule_type, net_days)
    return {
        "due_rule_type": normalize_due_rule_type(rule_type),
        "due_net_days": normalize_due_net_days(net_days),
        "due_rule_label": due_rule_label(rule_type, net_days),
        "due_date": due,
        "due_date_iso": due.isoformat(),
        "due_date_fmt": format_due_date(due),
    }


def _parse_iso_date(value):
    if not value:
        return None
    try:
        parts = str(value).strip().split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def resolve_invoice_due_date(invoice, settings=None):
    due = _parse_iso_date(invoice.get("due_date"))
    if due:
        return due

    invoice_date = _parse_iso_date(invoice.get("invoice_date"))
    if not invoice_date:
        return None

    if settings is None:
        import storage

        settings = storage.load_settings()

    rule_type = invoice.get("due_rule_type") or settings.get("due_rule_type")
    net_days = (
        invoice.get("due_net_days")
        if invoice.get("due_rule_type")
        else settings.get("due_net_days")
    )
    return compute_due_date(invoice_date, rule_type, net_days)


def due_countdown_for_invoice(invoice, today=None, settings=None):
    due = resolve_invoice_due_date(invoice, settings)
    if not due:
        return None

    today = today or date.today()
    delta = (due - today).days
    due_date_fmt = format_due_date(due)

    if delta > 0:
        suffix = "" if delta == 1 else "s"
        return {
            "kind": "due_soon",
            "days": delta,
            "label": f"Due in {delta} day{suffix}",
            "due_date_fmt": due_date_fmt,
        }
    if delta == 0:
        return {
            "kind": "due_today",
            "days": 0,
            "label": "Due today",
            "due_date_fmt": due_date_fmt,
        }

    overdue = abs(delta)
    suffix = "" if overdue == 1 else "s"
    return {
        "kind": "overdue",
        "days": overdue,
        "label": f"Overdue by {overdue} day{suffix}",
        "due_date_fmt": due_date_fmt,
    }


def sent_invoice_sort_key(invoice, settings=None):
    """Most overdue first, then nearest due date, then furthest out. No due date last."""
    due = resolve_invoice_due_date(invoice, settings)
    if due is None:
        return (1, date.max.isoformat(), int(invoice.get("invoice_number", 0)))
    return (0, due.isoformat(), int(invoice.get("invoice_number", 0)))
