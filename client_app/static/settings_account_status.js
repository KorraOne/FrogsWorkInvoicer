(function () {
    var configEl = document.getElementById("settings-account-config");
    if (!configEl) return;
    var config = JSON.parse(configEl.textContent || "{}");
    var statusUrl = config.statusUrl;
    if (!statusUrl) return;

    var statusEl = document.getElementById("entitlement-status");
    var servicesEl = document.getElementById("account-services-hint");
    var resubscribeEl = document.getElementById("resubscribe-row");

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    var LOCALE = "en-AU";
    var DATE_OPTS = { day: "numeric", month: "long", year: "numeric" };

    function formatDateTime(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return iso.slice(0, 16);
        return d.toLocaleString(LOCALE, Object.assign({}, DATE_OPTS, {
            hour: "numeric",
            minute: "2-digit"
        }));
    }

    function formatDate(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return iso.slice(0, 10);
        return d.toLocaleDateString(LOCALE, DATE_OPTS);
    }

    function accessUntil(ent) {
        return ent.access_until || ent.current_period_end || "";
    }

    function renderEntitlement(ent) {
        var html = "";
        var until = accessUntil(ent);
        if (ent.active) {
            if (ent.canceling) {
                html += '<p class="settings-link-hint">Cancelled';
                if (until) {
                    html += ". Available until " + escapeHtml(formatDate(until));
                }
                html += "</p>";
                if (ent.plan_interval) {
                    html += '<p class="settings-link-hint">' + escapeHtml(ent.plan_interval) + " plan</p>";
                }
            } else {
                html += '<p class="settings-link-hint">Active';
                if (ent.plan_interval) {
                    html += " · " + escapeHtml(ent.plan_interval) + " plan";
                }
                html += "</p>";
                if (until) {
                    html += '<p class="settings-link-hint">Renews ' + escapeHtml(formatDate(until)) + "</p>";
                }
            }
        } else if (ent.status === "canceled") {
            html += '<p class="settings-link-hint">Cancelled';
            if (until) {
                html += ". Ended " + escapeHtml(formatDate(until));
            }
            html += "</p>";
        } else if (ent.status) {
            html += '<p class="settings-link-hint">Status: ' + escapeHtml(ent.status) + "</p>";
        } else if (ent.last_verified_at) {
            html += '<p class="settings-link-hint">No active subscription</p>";
        } else {
            html += '<p class="settings-link-hint">Not verified yet. Use Verify subscription.</p>";
        }
        if (ent.last_verified_at) {
            html += '<p class="settings-link-hint">Last verified ' + escapeHtml(formatDateTime(ent.last_verified_at)) + "</p>";
        }
        return html;
    }

    function setServicesHint(ok) {
        if (!servicesEl) return;
        if (ok) {
            servicesEl.textContent = "";
            servicesEl.classList.add("hidden");
        } else {
            servicesEl.textContent = "Account server unavailable. Check your connection.";
            servicesEl.classList.remove("hidden");
        }
    }

    function applyStatus(data) {
        if (!statusEl || !data || !data.authenticated) return;
        var ent = data.entitlement || {};
        statusEl.innerHTML = renderEntitlement(ent);
        setServicesHint(data.account_services_ok);
        if (resubscribeEl) {
            resubscribeEl.classList.toggle("hidden", !!ent.active);
        }
    }

    fetch(statusUrl, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(applyStatus)
        .catch(function () {
            if (!statusEl) return;
            statusEl.innerHTML = '<p class="settings-link-hint settings-link-hint--warn">Couldn\'t check subscription. Try Verify subscription.</p>';
            setServicesHint(false);
        });
})();
