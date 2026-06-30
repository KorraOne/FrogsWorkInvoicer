const INSTALL_ID_RE = /^[a-f0-9]{64}$/;

const EVENT_COLUMNS = {
  first_invoice: "first_invoice_at",
  first_customer: "first_customer_at",
  first_invoice_sent: "first_invoice_sent_at",
  first_paid_marked: "first_paid_marked_at",
  uninstall: "uninstalled_at",
};

const EVENT_FLAGS = {
  backup_export: "has_backup_export",
  backup_import: "has_backup_import",
};

export function isValidInstallId(installId) {
  return typeof installId === "string" && INSTALL_ID_RE.test(installId);
}

function nowIso() {
  return new Date().toISOString();
}

function boolInt(value) {
  return value ? 1 : 0;
}

function pickSnapshot(body) {
  return body.usage_snapshot && typeof body.usage_snapshot === "object"
    ? body.usage_snapshot
    : body;
}

function snapshotFields(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return {};
  }
  const out = {};
  const map = [
    ["gst_registered", "gst_registered", boolInt],
    ["welcome_complete", "welcome_complete", boolInt],
    ["lifetime_invoice_count", "lifetime_invoice_count", (v) => Number(v) || 0],
    ["lifetime_ex_gst", "lifetime_ex_gst", String],
    ["customer_count", "customer_count", (v) => Number(v) || 0],
    ["invoices_sent", "invoices_sent", (v) => Number(v) || 0],
    ["invoices_paid", "invoices_paid", (v) => Number(v) || 0],
    ["invoices_not_sent", "invoices_not_sent", (v) => Number(v) || 0],
    ["due_rule_type", "due_rule_type", String],
    ["custom_pdf_folder", "custom_pdf_folder", boolInt],
    ["days_since_last_invoice", "days_since_last_invoice", (v) =>
      v === null || v === undefined ? null : Number(v)],
    ["trial_gate_hit", "trial_gate_hit", String],
  ];
  for (const [key, col, fn] of map) {
    if (snapshot[key] !== undefined && snapshot[key] !== null) {
      out[col] = fn(snapshot[key]);
    }
  }
  return out;
}

export async function upsertHeartbeat(db, body) {
  const installId = (body.install_id || "").trim().toLowerCase();
  if (!isValidInstallId(installId)) {
    throw new Error("Invalid install_id.");
  }

  const now = nowIso();
  const appVersion = (body.app_version || "").trim();
  const isPackaged = body.is_packaged === undefined ? null : boolInt(body.is_packaged);
  const snapshot = pickSnapshot(body);
  const fields = snapshotFields(snapshot);

  const existing = await db
    .prepare("SELECT install_id, app_version_first FROM installs WHERE install_id = ?")
    .bind(installId)
    .first();

  if (!existing) {
    const cols = [
      "install_id",
      "first_seen_at",
      "last_seen_at",
      "app_version_first",
      "app_version_last",
      "is_packaged",
    ];
    const vals = [installId, now, now, appVersion || null, appVersion || null, isPackaged];
    for (const [col, val] of Object.entries(fields)) {
      cols.push(col);
      vals.push(val);
    }
    const placeholders = cols.map(() => "?").join(", ");
    await db
      .prepare(`INSERT INTO installs (${cols.join(", ")}) VALUES (${placeholders})`)
      .bind(...vals)
      .run();
    return { created: true };
  }

  const sets = ["last_seen_at = ?"];
  const binds = [now];
  if (appVersion) {
    sets.push("app_version_last = ?");
    binds.push(appVersion);
    if (!existing.app_version_first) {
      sets.push("app_version_first = ?");
      binds.push(appVersion);
    }
  }
  if (isPackaged !== null) {
    sets.push("is_packaged = ?");
    binds.push(isPackaged);
  }
  for (const [col, val] of Object.entries(fields)) {
    sets.push(`${col} = ?`);
    binds.push(val);
  }
  binds.push(installId);
  await db
    .prepare(`UPDATE installs SET ${sets.join(", ")} WHERE install_id = ?`)
    .bind(...binds)
    .run();
  return { created: false };
}

export async function recordEvent(db, body) {
  const installId = (body.install_id || "").trim().toLowerCase();
  const event = (body.event || "").trim();
  if (!isValidInstallId(installId)) {
    throw new Error("Invalid install_id.");
  }
  if (!event) {
    throw new Error("event is required.");
  }

  const now = nowIso();
  const appVersion = (body.app_version || "").trim();

  const existing = await db
    .prepare("SELECT install_id FROM installs WHERE install_id = ?")
    .bind(installId)
    .first();

  if (!existing) {
    await db
      .prepare(
        `INSERT INTO installs (install_id, first_seen_at, last_seen_at, app_version_first, app_version_last)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(installId, now, now, appVersion || null, appVersion || null)
      .run();
  }

  const col = EVENT_COLUMNS[event];
  if (col) {
    await db
      .prepare(
        `UPDATE installs SET ${col} = COALESCE(${col}, ?), last_seen_at = ? WHERE install_id = ?`
      )
      .bind(now, now, installId)
      .run();
    return { event, recorded: true };
  }

  const flag = EVENT_FLAGS[event];
  if (flag) {
    await db
      .prepare(`UPDATE installs SET ${flag} = 1, last_seen_at = ? WHERE install_id = ?`)
      .bind(now, installId)
      .run();
    return { event, recorded: true };
  }

  throw new Error(`Unknown event: ${event}`);
}

export function subscriptionStateFromEntitlements(sub) {
  if (sub.active && sub.canceling) return "canceling";
  if (sub.active) return "active";
  if (sub.status === "canceled") return "canceled";
  return "none";
}

export async function linkInstallOnRegister(db, installId, userId, signupSnapshot) {
  if (!installId || !isValidInstallId(installId)) {
    return;
  }
  const now = nowIso();
  const snap = signupSnapshot || {};
  const signupExGst =
    snap.lifetime_ex_gst_total !== undefined
      ? String(snap.lifetime_ex_gst_total)
      : snap.lifetime_ex_gst !== undefined
        ? String(snap.lifetime_ex_gst)
        : null;

  await db.prepare("UPDATE users SET install_id = ? WHERE id = ?").bind(installId, userId).run();

  const existing = await db
    .prepare("SELECT install_id FROM installs WHERE install_id = ?")
    .bind(installId)
    .first();

  const signupFields = {
    signup_invoice_count:
      snap.lifetime_invoice_count !== undefined ? Number(snap.lifetime_invoice_count) : null,
    signup_ex_gst: signupExGst,
    signup_gst_registered:
      snap.gst_registered !== undefined ? boolInt(snap.gst_registered) : null,
    trial_gate_hit: snap.trial_gate_hit || null,
    account_created_at: now,
    user_id: userId,
    last_seen_at: now,
  };

  if (!existing) {
    const cols = ["install_id", "first_seen_at", ...Object.keys(signupFields)];
    const vals = [installId, now, ...Object.values(signupFields)];
    await db
      .prepare(
        `INSERT INTO installs (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")})`
      )
      .bind(...vals)
      .run();
    return;
  }

  const sets = [];
  const binds = [];
  for (const [col, val] of Object.entries(signupFields)) {
    if (col.endsWith("_at") || col === "user_id") {
      sets.push(`${col} = COALESCE(${col}, ?)`);
    } else if (col === "trial_gate_hit") {
      sets.push(`${col} = COALESCE(${col}, ?)`);
    } else {
      sets.push(`${col} = ?`);
    }
    binds.push(val);
  }
  binds.push(installId);
  await db
    .prepare(`UPDATE installs SET ${sets.join(", ")} WHERE install_id = ?`)
    .bind(...binds)
    .run();
}

export async function updateSubscriptionMilestones(db, user, sub) {
  const installId = user.install_id;
  if (!installId || !isValidInstallId(installId)) {
    return;
  }

  const row = await db
    .prepare("SELECT * FROM installs WHERE install_id = ?")
    .bind(installId)
    .first();
  if (!row) {
    return;
  }

  const now = nowIso();
  const state = subscriptionStateFromEntitlements(sub);
  const sets = ["subscription_state = ?"];
  const binds = [state];

  if (sub.active && !row.subscribed_at) {
    sets.push("subscribed_at = ?");
    binds.push(now);
    if (sub.plan_interval) {
      sets.push("plan_interval = ?");
      binds.push(sub.plan_interval);
    }
    if (row.lifetime_invoice_count != null) {
      sets.push("subscribe_invoice_count = ?");
      binds.push(row.lifetime_invoice_count);
    }
    if (row.lifetime_ex_gst != null) {
      sets.push("subscribe_ex_gst = ?");
      binds.push(row.lifetime_ex_gst);
    }
  }

  if (sub.active && sub.canceling && !row.cancel_scheduled_at) {
    sets.push("cancel_scheduled_at = ?");
    binds.push(now);
  }

  if (!sub.active && row.subscribed_at && !row.unsubscribed_at) {
    sets.push("unsubscribed_at = ?");
    binds.push(now);
  }

  if (sub.active && row.unsubscribed_at && !row.resubscribed_at) {
    sets.push("resubscribed_at = ?");
    binds.push(now);
  }

  if (sub.plan_interval && sub.active) {
    sets.push("plan_interval = ?");
    binds.push(sub.plan_interval);
  }

  binds.push(installId);
  await db
    .prepare(`UPDATE installs SET ${sets.join(", ")} WHERE install_id = ?`)
    .bind(...binds)
    .run();
}
