(function (global) {
    "use strict";

    function parseIsoLocal(iso) {
        var parts = (iso || "").split("-");
        if (parts.length !== 3) {
            return new Date();
        }
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }

    function formatDueDate(d) {
        return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
    }

    function endOfWeekSunday(d) {
        var weekday = (d.getDay() + 6) % 7;
        return new Date(d.getFullYear(), d.getMonth(), d.getDate() + (6 - weekday));
    }

    function computeDueDate(invoiceDateIso, ruleType, netDays, fixedDateIso) {
        var invoiceDate = parseIsoLocal(invoiceDateIso);
        if (ruleType === "fixed_date" && fixedDateIso) {
            var fixed = parseIsoLocal(fixedDateIso);
            return fixed < invoiceDate ? invoiceDate : fixed;
        }
        if (ruleType === "net_days") {
            var days = Math.max(1, parseInt(netDays, 10) || 14);
            return new Date(
                invoiceDate.getFullYear(),
                invoiceDate.getMonth(),
                invoiceDate.getDate() + days
            );
        }
        if (ruleType === "end_next_week") {
            var sunday = endOfWeekSunday(invoiceDate);
            return new Date(sunday.getFullYear(), sunday.getMonth(), sunday.getDate() + 7);
        }
        return new Date(invoiceDate.getFullYear(), invoiceDate.getMonth() + 2, 0);
    }

    function initDueRuleUi(config) {
        var select = document.getElementById("due_rule_type");
        if (!select) {
            return;
        }

        var panels = document.querySelectorAll(".due-rule-panel");
        var netDaysInput = document.getElementById("due_net_days");
        var fixedDateInput = document.getElementById("due_fixed_date");
        var previewEl = document.getElementById("due-date-preview");
        var invoiceDateIso = (config && config.invoiceDateIso) || new Date().toISOString().slice(0, 10);

        function syncPanels() {
            var active = select.value;
            panels.forEach(function (panel) {
                panel.hidden = panel.getAttribute("data-panel") !== active;
            });
            if (netDaysInput) {
                netDaysInput.disabled = active !== "net_days";
            }
            if (fixedDateInput) {
                fixedDateInput.disabled = active !== "fixed_date";
                fixedDateInput.min = invoiceDateIso;
            }
        }

        function updatePreview() {
            if (!previewEl) {
                return;
            }
            var fixed = fixedDateInput ? fixedDateInput.value : "";
            previewEl.textContent = formatDueDate(
                computeDueDate(
                    invoiceDateIso,
                    select.value,
                    netDaysInput ? netDaysInput.value : "14",
                    fixed
                )
            );
        }

        function refresh() {
            syncPanels();
            updatePreview();
        }

        select.addEventListener("change", refresh);
        if (netDaysInput) {
            netDaysInput.addEventListener("input", updatePreview);
            netDaysInput.addEventListener("change", updatePreview);
        }
        if (fixedDateInput) {
            fixedDateInput.addEventListener("change", updatePreview);
        }
        refresh();
    }

    global.initDueRuleUi = initDueRuleUi;
})(window);
