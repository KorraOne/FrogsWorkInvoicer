"""Privacy-friendly aggregate metrics (mirrors worker/src/metrics.js)."""


def _scalar(db, sql, params=()):
    row = db.execute(sql, params).fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def _pct(part, whole):
    if not whole:
        return None
    return round(1000 * part / whole) / 10


def _avg(total, count):
    if not count:
        return None
    return round(100 * total / count) / 100


def build_metrics_summary(db):
    accounts_total = _scalar(db, "SELECT COUNT(*) FROM users")
    accounts_active = _scalar(
        db,
        "SELECT COUNT(*) FROM users WHERE account_status = 'active' AND stripe_customer_id IS NOT NULL",
    )
    accounts_pending = _scalar(
        db, "SELECT COUNT(*) FROM users WHERE account_status = 'pending_payment'"
    )
    tier_local = _scalar(
        db,
        "SELECT COUNT(*) FROM users WHERE account_status = 'active' AND storage_tier = 'local'",
    )
    tier_cloud = _scalar(
        db,
        "SELECT COUNT(*) FROM users WHERE account_status = 'active' AND storage_tier = 'cloud'",
    )
    subscribed = _scalar(db, "SELECT COUNT(*) FROM users WHERE subscribed_at IS NOT NULL")
    cancel_scheduled = _scalar(
        db,
        "SELECT COUNT(*) FROM users WHERE cancel_scheduled_at IS NOT NULL AND unsubscribed_at IS NULL",
    )
    unsubscribed = _scalar(db, "SELECT COUNT(*) FROM users WHERE unsubscribed_at IS NOT NULL")

    inv_rows = db.execute(
        "SELECT user_id, COUNT(*) AS n FROM doc_invoices GROUP BY user_id"
    ).fetchall()
    inv_sum = sum(int(r["n"]) for r in inv_rows)
    cloud_docs = _scalar(
        db,
        """SELECT COUNT(DISTINCT user_id) FROM (
             SELECT user_id FROM doc_invoices
             UNION SELECT user_id FROM doc_customers
             UNION SELECT user_id FROM doc_businesses
             UNION SELECT user_id FROM doc_settings
           )""",
    )

    due_types = {
        str(r[0]): int(r[1])
        for r in db.execute(
            """SELECT COALESCE(json_extract(data_json, '$.due_rule_type'), 'unknown'), COUNT(*)
               FROM doc_invoices GROUP BY 1"""
        ).fetchall()
    }

    cust_total = _scalar(db, "SELECT COUNT(*) FROM doc_customers")
    inline_c = _scalar(
        db,
        "SELECT COUNT(*) FROM doc_customers WHERE json_extract(data_json, '$.created_via') = 'inline'",
    )
    logo_users = _scalar(
        db,
        """SELECT COUNT(DISTINCT user_id) FROM doc_businesses
           WHERE json_extract(data_json, '$.logo_enabled') = 1
              OR (json_extract(data_json, '$.logo_b64') IS NOT NULL
                  AND length(json_extract(data_json, '$.logo_b64')) > 20)""",
    )
    outbox_sent = _scalar(db, "SELECT COUNT(*) FROM email_outbox WHERE status = 'sent'")
    outbox_failed = _scalar(db, "SELECT COUNT(*) FROM email_outbox WHERE status = 'failed'")

    device_rows = db.execute(
        "SELECT user_id, COUNT(*) AS n FROM account_devices GROUP BY user_id"
    ).fetchall()
    device_sum = sum(int(r["n"]) for r in device_rows)
    platforms = {
        str(r[0]): int(r[1])
        for r in db.execute(
            "SELECT platform, COUNT(*) FROM account_devices GROUP BY platform"
        ).fetchall()
    }

    return {
        "accounts": {
            "total": accounts_total,
            "active_paid": accounts_active,
            "pending_payment": accounts_pending,
            "tier_local": tier_local,
            "tier_cloud": tier_cloud,
            "cloud_with_docs": cloud_docs,
        },
        "subscription": {
            "ever_subscribed": subscribed,
            "cancel_scheduled": cancel_scheduled,
            "unsubscribed": unsubscribed,
            "cancel_scheduled_pct": _pct(cancel_scheduled, subscribed),
            "churn_pct": _pct(unsubscribed, subscribed),
        },
        "invoices": {
            "total": inv_sum,
            "avg_per_cloud_account": _avg(inv_sum, cloud_docs or 1),
            "due_rule_types": due_types,
        },
        "customers": {
            "total": cust_total,
            "created_via_inline": inline_c,
            "inline_pct": _pct(inline_c, cust_total),
        },
        "businesses": {
            "accounts_with_logo": logo_users,
            "logo_adoption_pct": _pct(logo_users, cloud_docs),
        },
        "email": {
            "outbox_sent": outbox_sent,
            "outbox_failed": outbox_failed,
            "send_success_pct": _pct(outbox_sent, outbox_sent + outbox_failed),
        },
        "devices": {
            "accounts_reporting": len(device_rows),
            "avg_per_reporting_account": _avg(device_sum, len(device_rows) or 1),
            "platforms": platforms,
        },
    }
