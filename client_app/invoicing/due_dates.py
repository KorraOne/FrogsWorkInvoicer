"""Invoice due date rules — compute concrete due dates from settings or per-invoice choices."""

import calendar
import re
from datetime import date, timedelta

VALID_DUE_RULE_TYPES = ("net_days", "end_next_week", "end_next_month", "fixed_date")
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


def _parse_iso_date(value):
    if not value:
        return None
    try:
        parts = str(value).strip().split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def normalize_due_fixed_date(value, invoice_date=None, default_days=DEFAULT_DUE_NET_DAYS):
    base = invoice_date or date.today()
    due = _parse_iso_date(value)
    if not due:
        due = base + timedelta(days=default_days)
    if due < base:
        due = base
    return due.isoformat()


def last_day_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def end_of_week_sunday(d):
    return d + timedelta(days=(6 - d.weekday()))


def compute_due_date(invoice_date, rule_type, net_days=DEFAULT_DUE_NET_DAYS, fixed_date=None):
    rule_type = normalize_due_rule_type(rule_type)
    if rule_type == "fixed_date":
        due = _parse_iso_date(fixed_date) or (invoice_date + timedelta(days=normalize_due_net_days(net_days)))
        if due < invoice_date:
            due = invoice_date
        return due
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


def due_rule_label(rule_type, net_days=DEFAULT_DUE_NET_DAYS, fixed_date=None):
    rule_type = normalize_due_rule_type(rule_type)
    if rule_type == "net_days":
        days = normalize_due_net_days(net_days)
        suffix = "" if days == 1 else "s"
        return f"Net {days} day{suffix}"
    if rule_type == "end_next_week":
        return "End of next week"
    if rule_type == "end_next_month":
        return "End of next month"
    due = _parse_iso_date(fixed_date)
    if due:
        return format_due_date(due)
    return "Specific date"


def format_due_date(d):
    return d.strftime("%d %B %Y")


def due_rule_from_settings(settings):
    """Default due rule stored in settings (no specific calendar date)."""
    rule_type = normalize_due_rule_type(settings.get("due_rule_type"))
    if rule_type == "fixed_date":
        rule_type = DEFAULT_DUE_RULE_TYPE
    return {
        "due_rule_type": rule_type,
        "due_net_days": normalize_due_net_days(settings.get("due_net_days")),
        "due_fixed_date": "",
    }


def default_due_prefs():
    return {
        "due_rule_type": DEFAULT_DUE_RULE_TYPE,
        "due_net_days": DEFAULT_DUE_NET_DAYS,
        "due_fixed_date": "",
    }


def due_prefs_still_valid(prefs, invoice_date=None):
    invoice_date = invoice_date or date.today()
    if prefs.get("due_rule_type") != "fixed_date":
        return True
    fixed = _parse_iso_date(prefs.get("due_fixed_date"))
    return bool(fixed and fixed >= invoice_date)


def due_prefs_for_new_invoice(settings, invoice_date=None):
    """Due rule defaults for a new create-invoice form."""
    invoice_date = invoice_date or date.today()
    last = {
        "due_rule_type": (settings.get("last_due_rule_type") or "").strip(),
        "due_net_days": settings.get("last_due_net_days"),
        "due_fixed_date": settings.get("last_due_fixed_date") or "",
    }
    if last["due_rule_type"]:
        prefs = {
            "due_rule_type": normalize_due_rule_type(last["due_rule_type"]),
            "due_net_days": normalize_due_net_days(last["due_net_days"]),
            "due_fixed_date": last["due_fixed_date"],
        }
        if due_prefs_still_valid(prefs, invoice_date):
            if prefs["due_rule_type"] == "fixed_date":
                prefs["due_fixed_date"] = normalize_due_fixed_date(
                    prefs["due_fixed_date"], invoice_date, prefs["due_net_days"]
                )
            return prefs

    prefs = due_rule_from_settings(settings)
    prefs["due_fixed_date"] = normalize_due_fixed_date(
        None, invoice_date, prefs["due_net_days"]
    )
    return prefs


def save_last_due_prefs(settings, rule):
    settings["last_due_rule_type"] = rule["due_rule_type"]
    settings["last_due_net_days"] = normalize_due_net_days(rule.get("due_net_days"))
    if rule["due_rule_type"] == "fixed_date":
        settings["last_due_fixed_date"] = rule.get("due_fixed_date") or ""
    else:
        settings["last_due_fixed_date"] = ""


def due_rule_from_form_data(form, settings=None):
    settings = settings or {}
    invoice_date = date.today()
    defaults = due_prefs_for_new_invoice(settings, invoice_date)
    rule_type = normalize_due_rule_type(
        form.get("due_rule_type") or defaults["due_rule_type"]
    )
    net_days = normalize_due_net_days(form.get("due_net_days"), defaults["due_net_days"])
    fixed = form.get("due_fixed_date") or defaults.get("due_fixed_date") or ""
    return {
        "due_rule_type": rule_type,
        "due_net_days": net_days,
        "due_fixed_date": normalize_due_fixed_date(fixed, invoice_date, net_days),
    }


def merge_due_rule_into_form(form, settings):
    if form.get("due_rule_type"):
        prefs = due_rule_from_form_data(form, settings)
    else:
        prefs = due_prefs_for_new_invoice(settings)
    form["due_rule_type"] = prefs["due_rule_type"]
    form["due_net_days"] = str(prefs["due_net_days"])
    form["due_fixed_date"] = prefs["due_fixed_date"]
    return form


def due_rule_template_context(invoice_date=None, settings=None, form=None):
    invoice_date = invoice_date or date.today()
    settings = settings or {}
    rule = due_rule_from_form_data(form, settings) if form is not None else due_rule_from_settings(settings)
    summary = invoice_due_summary(
        invoice_date,
        rule["due_rule_type"],
        rule["due_net_days"],
        rule["due_fixed_date"],
    )
    return {
        "due_rule_type": summary["due_rule_type"],
        "due_net_days": summary["due_net_days"],
        "due_fixed_date": rule["due_fixed_date"],
        "due_date_preview": summary["due_date_fmt"],
        "invoice_date_iso": invoice_date.isoformat(),
    }


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
    if settings.get("due_rule_type") == "fixed_date":
        settings["due_rule_type"] = DEFAULT_DUE_RULE_TYPE
        changed = True
    for key in ("last_due_rule_type", "last_due_fixed_date"):
        if key not in settings:
            settings[key] = ""
            changed = True
    if "last_due_net_days" not in settings:
        settings["last_due_net_days"] = DEFAULT_DUE_NET_DAYS
        changed = True
    return changed


def invoice_due_summary(invoice_date, rule_type, net_days, fixed_date=None):
    rule_type = normalize_due_rule_type(rule_type)
    net_days = normalize_due_net_days(net_days)
    if rule_type == "fixed_date":
        fixed_date = normalize_due_fixed_date(fixed_date, invoice_date, net_days)
    due = compute_due_date(invoice_date, rule_type, net_days, fixed_date)
    return {
        "due_rule_type": rule_type,
        "due_net_days": net_days,
        "due_fixed_date": fixed_date if rule_type == "fixed_date" else None,
        "due_rule_label": due_rule_label(rule_type, net_days, fixed_date),
        "due_date": due,
        "due_date_iso": due.isoformat(),
        "due_date_fmt": format_due_date(due),
    }


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
    fixed_date = invoice.get("due_fixed_date") or settings.get("due_fixed_date")
    return compute_due_date(invoice_date, rule_type, net_days, fixed_date)


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
