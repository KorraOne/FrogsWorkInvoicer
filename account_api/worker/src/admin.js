function pct(num, den) {
  if (!den) return null;
  return Math.round((1000 * num) / den) / 10;
}

function median(values) {
  const nums = values.filter((v) => v != null && !Number.isNaN(v)).sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  if (nums.length % 2) return nums[mid];
  return Math.round((nums[mid - 1] + nums[mid]) / 2);
}

function daysBetween(start, end) {
  if (!start || !end) return null;
  const a = new Date(start).getTime();
  const b = new Date(end).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / 86400000);
}

async function scalar(db, sql) {
  const row = await db.prepare(sql).first();
  const key = Object.keys(row || {})[0];
  return row ? row[key] : 0;
}

async function dayDiffs(db, startCol, endCol) {
  const rows = await db
    .prepare(
      `SELECT ${startCol} AS start_at, ${endCol} AS end_at FROM installs
       WHERE ${startCol} IS NOT NULL AND ${endCol} IS NOT NULL`
    )
    .all();
  return (rows.results || []).map((r) => daysBetween(r.start_at, r.end_at));
}

export async function buildAdminSummary(db) {
  const installs = await scalar(db, "SELECT COUNT(*) AS c FROM installs");
  const accounts = await scalar(db, "SELECT COUNT(*) AS c FROM users");
  const firstInvoice = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE first_invoice_at IS NOT NULL"
  );
  const withAccount = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE account_created_at IS NOT NULL"
  );
  const subscribed = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE subscribed_at IS NOT NULL"
  );
  const cancelScheduled = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE cancel_scheduled_at IS NOT NULL"
  );
  const unsubscribed = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE unsubscribed_at IS NOT NULL"
  );
  const uninstalled = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE uninstalled_at IS NOT NULL"
  );
  const activeNow = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE subscription_state IN ('active', 'canceling')"
  );
  const atRisk = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE subscription_state = 'canceling'"
  );
  const stale30 = await scalar(
    db,
    `SELECT COUNT(*) AS c FROM installs
     WHERE datetime(last_seen_at) < datetime('now', '-30 days')`
  );
  const dormant90 = await scalar(
    db,
    `SELECT COUNT(*) AS c FROM installs
     WHERE datetime(last_seen_at) < datetime('now', '-90 days')`
  );
  const gstRegistered = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE gst_registered = 1"
  );
  const avgSignupInvoices = await scalar(
    db,
    "SELECT ROUND(AVG(signup_invoice_count), 1) AS c FROM installs WHERE signup_invoice_count IS NOT NULL"
  );
  const avgSignupExGst = await scalar(
    db,
    "SELECT ROUND(AVG(CAST(signup_ex_gst AS REAL)), 2) AS c FROM installs WHERE signup_ex_gst IS NOT NULL"
  );
  const multiCustomer = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE customer_count >= 2"
  );
  const multiBusiness = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE business_count >= 2"
  );
  const sentAny = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE invoices_sent >= 1"
  );
  const customPdf = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE custom_pdf_folder = 1"
  );
  const backupExport = await scalar(
    db,
    "SELECT COUNT(*) AS c FROM installs WHERE has_backup_export = 1"
  );

  const planRows = await db
    .prepare(
      `SELECT plan_interval AS plan_key, COUNT(*) AS count FROM installs
       WHERE subscribed_at IS NOT NULL AND plan_interval IS NOT NULL AND plan_interval != ''
       GROUP BY plan_interval`
    )
    .all();
  const trialGateRows = await db
    .prepare(
      `SELECT trial_gate_hit AS gate, COUNT(*) AS count FROM installs
       WHERE trial_gate_hit IS NOT NULL AND trial_gate_hit != ''
       GROUP BY trial_gate_hit`
    )
    .all();
  const versionRows = await db
    .prepare(
      `SELECT app_version_last AS version, COUNT(*) AS count FROM installs
       WHERE app_version_last IS NOT NULL AND app_version_last != ''
       GROUP BY app_version_last ORDER BY count DESC LIMIT 10`
    )
    .all();

  return {
    counts: {
      installs,
      accounts,
      first_invoice: firstInvoice,
      subscribed,
      cancel_scheduled: cancelScheduled,
      unsubscribed,
      uninstalled,
      active_subscribers: activeNow,
      at_risk_canceling: atRisk,
      stale_30d: stale30,
      dormant_90d: dormant90,
    },
    rates: {
      install_to_invoice_pct: pct(firstInvoice, installs),
      invoice_to_account_pct: pct(withAccount, firstInvoice),
      account_to_subscribed_pct: pct(subscribed, withAccount),
      subscribed_to_cancel_pct: pct(cancelScheduled, subscribed),
      subscribed_to_churn_pct: pct(unsubscribed, subscribed),
      uninstall_pct: pct(uninstalled, installs),
      gst_registered_pct: pct(gstRegistered, installs),
      multi_customer_pct: pct(multiCustomer, installs),
      multi_business_pct: pct(multiBusiness, installs),
      sent_any_pct: pct(sentAny, installs),
      custom_pdf_pct: pct(customPdf, installs),
      backup_export_pct: pct(backupExport, installs),
    },
    medians_days: {
      install_to_first_invoice: median(await dayDiffs(db, "first_seen_at", "first_invoice_at")),
      install_to_subscribe: median(await dayDiffs(db, "first_seen_at", "subscribed_at")),
      account_to_subscribe: median(await dayDiffs(db, "account_created_at", "subscribed_at")),
      subscription_tenure: median(await dayDiffs(db, "subscribed_at", "unsubscribed_at")),
    },
    signup: {
      avg_invoice_count: avgSignupInvoices,
      avg_ex_gst: avgSignupExGst,
      trial_gate: trialGateRows.results || [],
      plan_interval: planRows.results || [],
    },
    versions: versionRows.results || [],
    notes: {
      uninstall_undercount:
        "Explicit uninstalls only fire when the user runs the Windows uninstaller. Deleting the app folder is not detected.",
      download_count: "See Cloudflare R2 / dashboard for installer downloads.",
    },
  };
}

function fmtPct(value) {
  if (value == null) return "—";
  return `${value}%`;
}

function fmtNum(value) {
  if (value == null || value === "") return "—";
  return String(value);
}

export function renderAdminHtml(summary, userTest = null) {
  const c = summary.counts;
  const r = summary.rates;
  const m = summary.medians_days;
  const s = summary.signup;

  const ut = userTest || { enabled: false, submissions: [], totalVideoBytes: 0 };
  const utEnabled = ut.enabled ? "checked" : "";
  const utRows = (ut.submissions || [])
    .map((row) => {
      const name = row.tester_name || "—";
      const hasVideo = Boolean(row.video_r2_key);
      const size = hasVideo
        ? row.video_bytes != null
          ? row.video_bytes < 1024 * 1024
            ? `${(row.video_bytes / 1024).toFixed(1)} KB`
            : `${(row.video_bytes / (1024 * 1024)).toFixed(1)} MB`
          : "—"
        : "No video";
      const answersLink = `/admin/api/user-test/submissions/${row.id}`;
      const videoLink = `/admin/api/user-test/submissions/${row.id}/video`;
      const videoCell = hasVideo
        ? ` · <a href="${videoLink}">Video</a>`
        : "";
      return `<tr>
        <td>${row.created_at || "—"}</td>
        <td>${name}</td>
        <td>${row.status || "—"}</td>
        <td>${size}</td>
        <td>
          <a href="${answersLink}" target="_blank" rel="noopener">Answers</a>${videoCell}
          · <button type="button" class="ut-delete" data-id="${row.id}">Delete</button>
        </td>
      </tr>`;
    })
    .join("");
  const utTotal =
    ut.totalVideoBytes < 1024 * 1024
      ? `${(ut.totalVideoBytes / 1024).toFixed(1)} KB`
      : `${(ut.totalVideoBytes / (1024 * 1024)).toFixed(1)} MB`;

  const trialGateHtml = (s.trial_gate || [])
    .map((row) => `<tr><td>${row.gate}</td><td>${row.count}</td></tr>`)
    .join("");
  const planHtml = (s.plan_interval || [])
    .map((row) => `<tr><td>${row.plan_key}</td><td>${row.count}</td></tr>`)
    .join("");
  const versionHtml = (summary.versions || [])
    .map((row) => `<tr><td>${row.version}</td><td>${row.count}</td></tr>`)
    .join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FrogsWork Admin</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 1.5rem; background: #f4f6f8; color: #1a1a1a; }
    h1 { margin-top: 0; }
    h2 { margin-top: 2rem; font-size: 1.1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }
    .card { background: #fff; border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .card .label { font-size: 0.8rem; color: #555; }
    .card .value { font-size: 1.5rem; font-weight: 600; margin-top: 0.25rem; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; margin-top: 0.75rem; }
    th, td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #eee; }
    th { background: #fafafa; font-size: 0.85rem; }
    .note { font-size: 0.85rem; color: #666; margin-top: 1rem; }
    a { color: #0b6; }
    .user-test-panel { background: #fff; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0 2rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .user-test-panel label { display: flex; align-items: center; gap: 0.5rem; font-weight: 600; }
    .user-test-panel .meta { font-size: 0.85rem; color: #555; margin-top: 0.5rem; }
    button.ut-delete { background: none; border: none; color: #c00; cursor: pointer; text-decoration: underline; font: inherit; padding: 0; }
  </style>
</head>
<body>
  <h1>FrogsWork analytics</h1>

  <div class="user-test-panel">
    <h2 style="margin-top:0">User testing</h2>
    <label>
      <input type="checkbox" id="ut-enabled" ${utEnabled}>
      Accepting submissions on frogswork.com/user-test.html
    </label>
    <p class="meta">Completed video storage (tracked): ${utTotal} · <a href="/admin/api/user-test/submissions">JSON</a></p>
    <table>
      <tr><th>Created</th><th>Name</th><th>Status</th><th>Size</th><th>Actions</th></tr>
      ${utRows || "<tr><td colspan=5>—</td></tr>"}
    </table>
  </div>

  <p class="note">R2 installer downloads: <a href="https://dash.cloudflare.com/" target="_blank" rel="noopener">Cloudflare dashboard</a> (not linked to install IDs).</p>

  <h2>Funnel</h2>
  <div class="grid">
    <div class="card"><div class="label">Installs</div><div class="value">${c.installs}</div></div>
    <div class="card"><div class="label">First invoice</div><div class="value">${c.first_invoice}</div></div>
    <div class="card"><div class="label">Accounts</div><div class="value">${c.accounts}</div></div>
    <div class="card"><div class="label">Subscribed</div><div class="value">${c.subscribed}</div></div>
  </div>
  <table>
    <tr><th>Step</th><th>Rate</th><th>Median days</th></tr>
    <tr><td>Install → invoice</td><td>${fmtPct(r.install_to_invoice_pct)}</td><td>${fmtNum(m.install_to_first_invoice)}</td></tr>
    <tr><td>Invoice → account</td><td>${fmtPct(r.invoice_to_account_pct)}</td><td>—</td></tr>
    <tr><td>Account → subscribed</td><td>${fmtPct(r.account_to_subscribed_pct)}</td><td>${fmtNum(m.account_to_subscribe)}</td></tr>
    <tr><td>Install → subscribe</td><td>—</td><td>${fmtNum(m.install_to_subscribe)}</td></tr>
  </table>

  <h2>Churn &amp; retention</h2>
  <div class="grid">
    <div class="card"><div class="label">Active subscribers</div><div class="value">${c.active_subscribers}</div></div>
    <div class="card"><div class="label">Cancel scheduled</div><div class="value">${c.cancel_scheduled}</div></div>
    <div class="card"><div class="label">Unsubscribed</div><div class="value">${c.unsubscribed}</div></div>
    <div class="card"><div class="label">At risk (canceling)</div><div class="value">${c.at_risk_canceling}</div></div>
    <div class="card"><div class="label">Explicit uninstalls</div><div class="value">${c.uninstalled}</div></div>
    <div class="card"><div class="label">Dormant 90d</div><div class="value">${c.dormant_90d}</div></div>
  </div>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Subscribed → cancel scheduled</td><td>${fmtPct(r.subscribed_to_cancel_pct)}</td></tr>
    <tr><td>Subscribed → churned</td><td>${fmtPct(r.subscribed_to_churn_pct)}</td></tr>
    <tr><td>Median subscription tenure (days)</td><td>${fmtNum(m.subscription_tenure)}</td></tr>
    <tr><td>Stale installs (30d)</td><td>${c.stale_30d}</td></tr>
  </table>
  <p class="note">${summary.notes.uninstall_undercount}</p>

  <h2>Signup snapshot</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Avg invoices at signup</td><td>${fmtNum(s.avg_invoice_count)}</td></tr>
    <tr><td>Avg ex GST at signup</td><td>${fmtNum(s.avg_ex_gst)}</td></tr>
    <tr><td>GST registered (latest heartbeat)</td><td>${fmtPct(r.gst_registered_pct)}</td></tr>
  </table>

  <h2>Trial gate at signup</h2>
  <table><tr><th>Gate</th><th>Count</th></tr>${trialGateHtml || "<tr><td colspan=2>—</td></tr>"}</table>

  <h2>Plan mix at subscribe</h2>
  <table><tr><th>Interval</th><th>Count</th></tr>${planHtml || "<tr><td colspan=2>—</td></tr>"}</table>

  <h2>Feature adoption</h2>
  <table>
    <tr><th>Feature</th><th>Rate</th></tr>
    <tr><td>2+ customers</td><td>${fmtPct(r.multi_customer_pct)}</td></tr>
    <tr><td>Marked ≥1 sent</td><td>${fmtPct(r.sent_any_pct)}</td></tr>
    <tr><td>Custom PDF folder</td><td>${fmtPct(r.custom_pdf_pct)}</td></tr>
    <tr><td>Backup export</td><td>${fmtPct(r.backup_export_pct)}</td></tr>
  </table>

  <h2>App versions (last seen)</h2>
  <table><tr><th>Version</th><th>Installs</th></tr>${versionHtml || "<tr><td colspan=2>—</td></tr>"}</table>

  <p class="note"><a href="/admin/api/summary">JSON summary</a></p>
  <script>
    (function () {
      var toggle = document.getElementById("ut-enabled");
      if (toggle) {
        toggle.addEventListener("change", function () {
          fetch("/admin/api/user-test/enabled", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: toggle.checked }),
            credentials: "same-origin",
          }).catch(function () {
            alert("Could not update user test setting.");
            toggle.checked = !toggle.checked;
          });
        });
      }
      document.querySelectorAll(".ut-delete").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-id");
          if (!id || !confirm("Delete this submission and its video?")) return;
          fetch("/admin/api/user-test/submissions/" + id, {
            method: "DELETE",
            credentials: "same-origin",
          }).then(function (res) {
            if (res.ok) location.reload();
            else alert("Delete failed.");
          });
        });
      });
    })();
  </script>
</body>
</html>`;
}

export function checkAdminAuth(request, adminPassword) {
  if (!adminPassword) {
    return { ok: false, response: new Response("Admin not configured.", { status: 503 }) };
  }
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Basic ")) {
    return {
      ok: false,
      response: new Response("Unauthorized", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="FrogsWork Admin"' },
      }),
    };
  }
  let decoded;
  try {
    decoded = atob(header.slice(6));
  } catch {
    return { ok: false, response: new Response("Unauthorized", { status: 401 }) };
  }
  const colon = decoded.indexOf(":");
  const password = colon >= 0 ? decoded.slice(colon + 1) : decoded;
  if (password !== adminPassword) {
    return {
      ok: false,
      response: new Response("Unauthorized", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="FrogsWork Admin"' },
      }),
    };
  }
  return { ok: true };
}
