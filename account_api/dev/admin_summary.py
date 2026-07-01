"""Admin dashboard summary and HTML (mirrors worker/src/admin.js)."""

from datetime import datetime


def _pct(num, den):
    if not den:
        return None
    return round(1000 * num / den) / 10


def _median(values):
    nums = sorted(v for v in values if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return round((nums[mid - 1] + nums[mid]) / 2)


def _days_between(start, end):
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((b - a).total_seconds() / 86400)


def _scalar(db, sql):
    row = db.execute(sql).fetchone()
    return row[0] if row else 0


def _day_diffs(db, start_col, end_col):
    rows = db.execute(
        f"""SELECT {start_col} AS start_at, {end_col} AS end_at FROM installs
            WHERE {start_col} IS NOT NULL AND {end_col} IS NOT NULL"""
    ).fetchall()
    return [_days_between(r["start_at"], r["end_at"]) for r in rows]


def build_admin_summary(db):
    installs = _scalar(db, "SELECT COUNT(*) FROM installs")
    accounts = _scalar(db, "SELECT COUNT(*) FROM users")
    first_invoice = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE first_invoice_at IS NOT NULL"
    )
    with_account = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE account_created_at IS NOT NULL"
    )
    subscribed = _scalar(db, "SELECT COUNT(*) FROM installs WHERE subscribed_at IS NOT NULL")
    cancel_scheduled = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE cancel_scheduled_at IS NOT NULL"
    )
    unsubscribed = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE unsubscribed_at IS NOT NULL"
    )
    uninstalled = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE uninstalled_at IS NOT NULL"
    )
    active_now = _scalar(
        db,
        "SELECT COUNT(*) FROM installs WHERE subscription_state IN ('active', 'canceling')",
    )
    at_risk = _scalar(
        db, "SELECT COUNT(*) FROM installs WHERE subscription_state = 'canceling'"
    )
    stale30 = _scalar(
        db,
        "SELECT COUNT(*) FROM installs WHERE datetime(last_seen_at) < datetime('now', '-30 days')",
    )
    dormant90 = _scalar(
        db,
        "SELECT COUNT(*) FROM installs WHERE datetime(last_seen_at) < datetime('now', '-90 days')",
    )
    gst_registered = _scalar(db, "SELECT COUNT(*) FROM installs WHERE gst_registered = 1")
    avg_signup_invoices = _scalar(
        db,
        "SELECT ROUND(AVG(signup_invoice_count), 1) FROM installs WHERE signup_invoice_count IS NOT NULL",
    )
    avg_signup_ex_gst = _scalar(
        db,
        "SELECT ROUND(AVG(CAST(signup_ex_gst AS REAL)), 2) FROM installs WHERE signup_ex_gst IS NOT NULL",
    )
    multi_customer = _scalar(db, "SELECT COUNT(*) FROM installs WHERE customer_count >= 2")
    multi_business = _scalar(db, "SELECT COUNT(*) FROM installs WHERE business_count >= 2")
    sent_any = _scalar(db, "SELECT COUNT(*) FROM installs WHERE invoices_sent >= 1")
    custom_pdf = _scalar(db, "SELECT COUNT(*) FROM installs WHERE custom_pdf_folder = 1")
    backup_export = _scalar(db, "SELECT COUNT(*) FROM installs WHERE has_backup_export = 1")

    plan_rows = [
        dict(r)
        for r in db.execute(
            """SELECT plan_interval AS interval, COUNT(*) AS count FROM installs
               WHERE subscribed_at IS NOT NULL AND plan_interval IS NOT NULL AND plan_interval != ''
               GROUP BY plan_interval"""
        ).fetchall()
    ]
    trial_gate_rows = [
        dict(r)
        for r in db.execute(
            """SELECT trial_gate_hit AS gate, COUNT(*) AS count FROM installs
               WHERE trial_gate_hit IS NOT NULL AND trial_gate_hit != ''
               GROUP BY trial_gate_hit"""
        ).fetchall()
    ]
    version_rows = [
        dict(r)
        for r in db.execute(
            """SELECT app_version_last AS version, COUNT(*) AS count FROM installs
               WHERE app_version_last IS NOT NULL AND app_version_last != ''
               GROUP BY app_version_last ORDER BY count DESC LIMIT 10"""
        ).fetchall()
    ]

    return {
        "counts": {
            "installs": installs,
            "accounts": accounts,
            "first_invoice": first_invoice,
            "subscribed": subscribed,
            "cancel_scheduled": cancel_scheduled,
            "unsubscribed": unsubscribed,
            "uninstalled": uninstalled,
            "active_subscribers": active_now,
            "at_risk_canceling": at_risk,
            "stale_30d": stale30,
            "dormant_90d": dormant90,
        },
        "rates": {
            "install_to_invoice_pct": _pct(first_invoice, installs),
            "invoice_to_account_pct": _pct(with_account, first_invoice),
            "account_to_subscribed_pct": _pct(subscribed, with_account),
            "subscribed_to_cancel_pct": _pct(cancel_scheduled, subscribed),
            "subscribed_to_churn_pct": _pct(unsubscribed, subscribed),
            "uninstall_pct": _pct(uninstalled, installs),
            "gst_registered_pct": _pct(gst_registered, installs),
            "multi_customer_pct": _pct(multi_customer, installs),
            "multi_business_pct": _pct(multi_business, installs),
            "sent_any_pct": _pct(sent_any, installs),
            "custom_pdf_pct": _pct(custom_pdf, installs),
            "backup_export_pct": _pct(backup_export, installs),
        },
        "medians_days": {
            "install_to_first_invoice": _median(_day_diffs(db, "first_seen_at", "first_invoice_at")),
            "install_to_subscribe": _median(_day_diffs(db, "first_seen_at", "subscribed_at")),
            "account_to_subscribe": _median(
                _day_diffs(db, "account_created_at", "subscribed_at")
            ),
            "subscription_tenure": _median(_day_diffs(db, "subscribed_at", "unsubscribed_at")),
        },
        "signup": {
            "avg_invoice_count": avg_signup_invoices,
            "avg_ex_gst": avg_signup_ex_gst,
            "trial_gate": trial_gate_rows,
            "plan_interval": plan_rows,
        },
        "versions": version_rows,
        "notes": {
            "uninstall_undercount": (
                "Explicit uninstalls only fire when the user runs the Windows uninstaller. "
                "Deleting the app folder is not detected."
            ),
            "download_count": "See Cloudflare R2 / dashboard for installer downloads.",
        },
    }


def _fmt_pct(value):
    if value is None:
        return "—"
    return f"{value}%"


def _fmt_num(value):
    if value is None or value == "":
        return "—"
    return str(value)


def render_admin_html(summary):
    c = summary["counts"]
    r = summary["rates"]
    m = summary["medians_days"]
    s = summary["signup"]

    trial_gate_html = "".join(
        f"<tr><td>{row['gate']}</td><td>{row['count']}</td></tr>"
        for row in s.get("trial_gate") or []
    ) or "<tr><td colspan=2>—</td></tr>"
    plan_html = "".join(
        f"<tr><td>{row['interval']}</td><td>{row['count']}</td></tr>"
        for row in s.get("plan_interval") or []
    ) or "<tr><td colspan=2>—</td></tr>"
    version_html = "".join(
        f"<tr><td>{row['version']}</td><td>{row['count']}</td></tr>"
        for row in summary.get("versions") or []
    ) or "<tr><td colspan=2>—</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FrogsWork Admin</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 1.5rem; background: #f4f6f8; color: #1a1a1a; }}
    h1 {{ margin-top: 0; }}
    h2 {{ margin-top: 2rem; font-size: 1.1rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }}
    .card {{ background: #fff; border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    .card .label {{ font-size: 0.8rem; color: #555; }}
    .card .value {{ font-size: 1.5rem; font-weight: 600; margin-top: 0.25rem; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; margin-top: 0.75rem; }}
    th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ background: #fafafa; font-size: 0.85rem; }}
    .note {{ font-size: 0.85rem; color: #666; margin-top: 1rem; }}
    a {{ color: #0b6; }}
  </style>
</head>
<body>
  <h1>FrogsWork analytics</h1>
  <p class="note">R2 installer downloads: <a href="https://dash.cloudflare.com/" target="_blank" rel="noopener">Cloudflare dashboard</a> (not linked to install IDs).</p>

  <h2>Funnel</h2>
  <div class="grid">
    <div class="card"><div class="label">Installs</div><div class="value">{c['installs']}</div></div>
    <div class="card"><div class="label">First invoice</div><div class="value">{c['first_invoice']}</div></div>
    <div class="card"><div class="label">Accounts</div><div class="value">{c['accounts']}</div></div>
    <div class="card"><div class="label">Subscribed</div><div class="value">{c['subscribed']}</div></div>
  </div>
  <table>
    <tr><th>Step</th><th>Rate</th><th>Median days</th></tr>
    <tr><td>Install → invoice</td><td>{_fmt_pct(r['install_to_invoice_pct'])}</td><td>{_fmt_num(m['install_to_first_invoice'])}</td></tr>
    <tr><td>Invoice → account</td><td>{_fmt_pct(r['invoice_to_account_pct'])}</td><td>—</td></tr>
    <tr><td>Account → subscribed</td><td>{_fmt_pct(r['account_to_subscribed_pct'])}</td><td>{_fmt_num(m['account_to_subscribe'])}</td></tr>
    <tr><td>Install → subscribe</td><td>—</td><td>{_fmt_num(m['install_to_subscribe'])}</td></tr>
  </table>

  <h2>Churn &amp; retention</h2>
  <div class="grid">
    <div class="card"><div class="label">Active subscribers</div><div class="value">{c['active_subscribers']}</div></div>
    <div class="card"><div class="label">Cancel scheduled</div><div class="value">{c['cancel_scheduled']}</div></div>
    <div class="card"><div class="label">Unsubscribed</div><div class="value">{c['unsubscribed']}</div></div>
    <div class="card"><div class="label">At risk (canceling)</div><div class="value">{c['at_risk_canceling']}</div></div>
    <div class="card"><div class="label">Explicit uninstalls</div><div class="value">{c['uninstalled']}</div></div>
    <div class="card"><div class="label">Dormant 90d</div><div class="value">{c['dormant_90d']}</div></div>
  </div>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Subscribed → cancel scheduled</td><td>{_fmt_pct(r['subscribed_to_cancel_pct'])}</td></tr>
    <tr><td>Subscribed → churned</td><td>{_fmt_pct(r['subscribed_to_churn_pct'])}</td></tr>
    <tr><td>Median subscription tenure (days)</td><td>{_fmt_num(m['subscription_tenure'])}</td></tr>
    <tr><td>Stale installs (30d)</td><td>{c['stale_30d']}</td></tr>
  </table>
  <p class="note">{summary['notes']['uninstall_undercount']}</p>

  <h2>Signup snapshot</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Avg invoices at signup</td><td>{_fmt_num(s['avg_invoice_count'])}</td></tr>
    <tr><td>Avg ex GST at signup</td><td>{_fmt_num(s['avg_ex_gst'])}</td></tr>
    <tr><td>GST registered (latest heartbeat)</td><td>{_fmt_pct(r['gst_registered_pct'])}</td></tr>
  </table>

  <h2>Trial gate at signup</h2>
  <table><tr><th>Gate</th><th>Count</th></tr>{trial_gate_html}</table>

  <h2>Plan mix at subscribe</h2>
  <table><tr><th>Interval</th><th>Count</th></tr>{plan_html}</table>

  <h2>Feature adoption</h2>
  <table>
    <tr><th>Feature</th><th>Rate</th></tr>
    <tr><td>2+ customers</td><td>{_fmt_pct(r['multi_customer_pct'])}</td></tr>
    <tr><td>2+ businesses</td><td>{_fmt_pct(r['multi_business_pct'])}</td></tr>
    <tr><td>Marked ≥1 sent</td><td>{_fmt_pct(r['sent_any_pct'])}</td></tr>
    <tr><td>Custom PDF folder</td><td>{_fmt_pct(r['custom_pdf_pct'])}</td></tr>
    <tr><td>Backup export</td><td>{_fmt_pct(r['backup_export_pct'])}</td></tr>
  </table>

  <h2>App versions (last seen)</h2>
  <table><tr><th>Version</th><th>Installs</th></tr>{version_html}</table>

  <p class="note"><a href="/admin/api/summary">JSON summary</a></p>
</body>
</html>"""
