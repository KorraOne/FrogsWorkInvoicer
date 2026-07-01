"""Install telemetry and admin analytics (mirrors worker/src/telemetry.js)."""

import re
from datetime import datetime, timezone

INSTALL_ID_RE = re.compile(r"^[a-f0-9]{64}$")

EVENT_COLUMNS = {
    "first_invoice": "first_invoice_at",
    "first_customer": "first_customer_at",
    "first_invoice_sent": "first_invoice_sent_at",
    "first_paid_marked": "first_paid_marked_at",
    "uninstall": "uninstalled_at",
}

EVENT_FLAGS = {
    "backup_export": "has_backup_export",
    "backup_import": "has_backup_import",
}


def is_valid_install_id(install_id):
    return bool(install_id and INSTALL_ID_RE.match(install_id))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _bool_int(value):
    return 1 if value else 0


def _pick_snapshot(body):
    snap = body.get("usage_snapshot")
    return snap if isinstance(snap, dict) else body


def _snapshot_fields(snapshot):
    if not isinstance(snapshot, dict):
        return {}
    out = {}
    mapping = [
        ("gst_registered", "gst_registered", _bool_int),
        ("welcome_complete", "welcome_complete", _bool_int),
        ("lifetime_invoice_count", "lifetime_invoice_count", lambda v: int(v or 0)),
        ("lifetime_ex_gst", "lifetime_ex_gst", str),
        ("customer_count", "customer_count", lambda v: int(v or 0)),
        ("business_count", "business_count", lambda v: int(v or 0)),
        ("invoices_sent", "invoices_sent", lambda v: int(v or 0)),
        ("invoices_paid", "invoices_paid", lambda v: int(v or 0)),
        ("invoices_not_sent", "invoices_not_sent", lambda v: int(v or 0)),
        ("due_rule_type", "due_rule_type", str),
        ("custom_pdf_folder", "custom_pdf_folder", _bool_int),
        (
            "days_since_last_invoice",
            "days_since_last_invoice",
            lambda v: None if v is None else int(v),
        ),
        ("trial_gate_hit", "trial_gate_hit", str),
    ]
    for key, col, fn in mapping:
        if key in snapshot and snapshot[key] is not None:
            out[col] = fn(snapshot[key])
    return out


def upsert_heartbeat(db, body):
    install_id = (body.get("install_id") or "").strip().lower()
    if not is_valid_install_id(install_id):
        raise ValueError("Invalid install_id.")

    now = _now_iso()
    app_version = (body.get("app_version") or "").strip()
    is_packaged = (
        None if body.get("is_packaged") is None else _bool_int(body.get("is_packaged"))
    )
    fields = _snapshot_fields(_pick_snapshot(body))

    existing = db.execute(
        "SELECT install_id, app_version_first FROM installs WHERE install_id = ?",
        (install_id,),
    ).fetchone()

    if not existing:
        cols = [
            "install_id",
            "first_seen_at",
            "last_seen_at",
            "app_version_first",
            "app_version_last",
            "is_packaged",
        ]
        vals = [install_id, now, now, app_version or None, app_version or None, is_packaged]
        for col, val in fields.items():
            cols.append(col)
            vals.append(val)
        placeholders = ", ".join("?" for _ in cols)
        db.execute(
            f"INSERT INTO installs ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        return {"created": True}

    sets = ["last_seen_at = ?"]
    binds = [now]
    if app_version:
        sets.append("app_version_last = ?")
        binds.append(app_version)
        if not existing["app_version_first"]:
            sets.append("app_version_first = ?")
            binds.append(app_version)
    if is_packaged is not None:
        sets.append("is_packaged = ?")
        binds.append(is_packaged)
    for col, val in fields.items():
        sets.append(f"{col} = ?")
        binds.append(val)
    binds.append(install_id)
    db.execute(
        f"UPDATE installs SET {', '.join(sets)} WHERE install_id = ?",
        binds,
    )
    return {"created": False}


def record_event(db, body):
    install_id = (body.get("install_id") or "").strip().lower()
    event = (body.get("event") or "").strip()
    if not is_valid_install_id(install_id):
        raise ValueError("Invalid install_id.")
    if not event:
        raise ValueError("event is required.")

    now = _now_iso()
    app_version = (body.get("app_version") or "").strip()

    existing = db.execute(
        "SELECT install_id FROM installs WHERE install_id = ?",
        (install_id,),
    ).fetchone()
    if not existing:
        db.execute(
            """INSERT INTO installs (install_id, first_seen_at, last_seen_at, app_version_first, app_version_last)
               VALUES (?, ?, ?, ?, ?)""",
            (install_id, now, now, app_version or None, app_version or None),
        )

    col = EVENT_COLUMNS.get(event)
    if col:
        db.execute(
            f"UPDATE installs SET {col} = COALESCE({col}, ?), last_seen_at = ? WHERE install_id = ?",
            (now, now, install_id),
        )
        return {"event": event, "recorded": True}

    flag = EVENT_FLAGS.get(event)
    if flag:
        db.execute(
            f"UPDATE installs SET {flag} = 1, last_seen_at = ? WHERE install_id = ?",
            (now, install_id),
        )
        return {"event": event, "recorded": True}

    raise ValueError(f"Unknown event: {event}")


def subscription_state_from_entitlements(sub):
    if sub.get("active") and sub.get("canceling"):
        return "canceling"
    if sub.get("active"):
        return "active"
    if sub.get("status") == "canceled":
        return "canceled"
    return "none"


def link_install_on_register(db, install_id, user_id, signup_snapshot):
    if not is_valid_install_id(install_id):
        return

    now = _now_iso()
    snap = signup_snapshot or {}
    signup_ex_gst = snap.get("lifetime_ex_gst_total", snap.get("lifetime_ex_gst"))
    if signup_ex_gst is not None:
        signup_ex_gst = str(signup_ex_gst)

    db.execute("UPDATE users SET install_id = ? WHERE id = ?", (install_id, user_id))

    existing = db.execute(
        "SELECT install_id FROM installs WHERE install_id = ?",
        (install_id,),
    ).fetchone()

    signup_fields = {
        "signup_invoice_count": snap.get("lifetime_invoice_count"),
        "signup_ex_gst": signup_ex_gst,
        "signup_gst_registered": _bool_int(snap.get("gst_registered"))
        if snap.get("gst_registered") is not None
        else None,
        "trial_gate_hit": snap.get("trial_gate_hit"),
        "account_created_at": now,
        "user_id": user_id,
        "last_seen_at": now,
    }

    if not existing:
        cols = ["install_id", "first_seen_at", *signup_fields.keys()]
        vals = [install_id, now, *signup_fields.values()]
        db.execute(
            f"INSERT INTO installs ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            vals,
        )
        return

    sets = []
    binds = []
    for col, val in signup_fields.items():
        if col in ("account_created_at", "user_id"):
            sets.append(f"{col} = COALESCE({col}, ?)")
        elif col == "trial_gate_hit":
            sets.append(f"{col} = COALESCE({col}, ?)")
        else:
            sets.append(f"{col} = ?")
        binds.append(val)
    binds.append(install_id)
    db.execute(
        f"UPDATE installs SET {', '.join(sets)} WHERE install_id = ?",
        binds,
    )


def update_subscription_milestones(db, user, sub):
    install_id = user["install_id"] if user else None
    if not is_valid_install_id(install_id):
        return

    row = db.execute("SELECT * FROM installs WHERE install_id = ?", (install_id,)).fetchone()
    if not row:
        return

    now = _now_iso()
    state = subscription_state_from_entitlements(sub)
    sets = ["subscription_state = ?"]
    binds = [state]

    if sub.get("active") and not row["subscribed_at"]:
        sets.append("subscribed_at = ?")
        binds.append(now)
        if sub.get("plan_interval"):
            sets.append("plan_interval = ?")
            binds.append(sub["plan_interval"])
        if row["lifetime_invoice_count"] is not None:
            sets.append("subscribe_invoice_count = ?")
            binds.append(row["lifetime_invoice_count"])
        if row["lifetime_ex_gst"] is not None:
            sets.append("subscribe_ex_gst = ?")
            binds.append(row["lifetime_ex_gst"])

    if sub.get("active") and sub.get("canceling") and not row["cancel_scheduled_at"]:
        sets.append("cancel_scheduled_at = ?")
        binds.append(now)

    if not sub.get("active") and row["subscribed_at"] and not row["unsubscribed_at"]:
        sets.append("unsubscribed_at = ?")
        binds.append(now)

    if sub.get("active") and row["unsubscribed_at"] and not row["resubscribed_at"]:
        sets.append("resubscribed_at = ?")
        binds.append(now)

    if sub.get("plan_interval") and sub.get("active"):
        sets.append("plan_interval = ?")
        binds.append(sub["plan_interval"])

    binds.append(install_id)
    db.execute(
        f"UPDATE installs SET {', '.join(sets)} WHERE install_id = ?",
        binds,
    )
