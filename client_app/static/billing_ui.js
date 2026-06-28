(function () {
    "use strict";

    function parseAmount(value) {
        var cleaned = String(value || "").replace(/[$,\s]/g, "");
        var num = parseFloat(cleaned);
        return isNaN(num) ? null : num;
    }

    function formatMoney(amount) {
        return "$" + amount.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    function blockConstants(block) {
        return {
            freeTier: parseFloat(block.dataset.freeTier) || 2000,
            feeRate: parseFloat(block.dataset.feeRate) || 0.0005,
        };
    }

    function computeFee(total, constants) {
        if (total <= constants.freeTier) {
            return 0;
        }
        return Math.round((total - constants.freeTier) * constants.feeRate * 100) / 100;
    }

    function invoiceFromFee(fee, constants) {
        if (fee <= 0) {
            return constants.freeTier;
        }
        return Math.round((constants.freeTier + fee / constants.feeRate) * 100) / 100;
    }

    function initFeeCalculator(block) {
        var input = block.querySelector(".fee-calculator-input");
        var result = block.querySelector(".fee-calculator-result");
        var breakdown = block.querySelector(".fee-calculator-breakdown");
        if (!input || !result) {
            return;
        }
        var constants = blockConstants(block);

        function update() {
            var total = parseAmount(input.value);
            if (total === null || total < 0) {
                result.textContent = "Enter a monthly total to see your fee.";
                if (breakdown) {
                    breakdown.textContent = "";
                }
                return;
            }
            var fee = computeFee(total, constants);
            result.innerHTML = "Platform fee: <strong>" + formatMoney(fee) + "</strong> for the month";
            if (breakdown) {
                if (total <= constants.freeTier) {
                    breakdown.textContent = "Within the $2,000 free allowance. No fee.";
                } else {
                    breakdown.textContent =
                        formatMoney(total - constants.freeTier) + " above free tier × 0.05% = " + formatMoney(fee);
                }
            }
        }

        input.addEventListener("input", update);
        update();
    }

    function initAllFeeCalculators() {
        document.querySelectorAll(".fee-calculator[data-billing-ui]").forEach(initFeeCalculator);
    }

    function initCapDualSync() {
        var fieldset = document.querySelector(".cap-choice-fieldset");
        if (!fieldset) {
            return;
        }
        var invoiceInput = fieldset.querySelector(".cap-invoice-input");
        var feeInput = fieldset.querySelector(".cap-fee-input");
        var radios = fieldset.querySelectorAll(".cap-choice-radio");
        if (!invoiceInput || !feeInput) {
            return;
        }

        var capBlock = document.querySelector(".fee-calculator[data-billing-ui]");
        var capConstants = capBlock ? blockConstants(capBlock) : { freeTier: 2000, feeRate: 0.0005 };
        var syncing = false;

        function syncCapInputs(source) {
            if (syncing) {
                return;
            }
            syncing = true;
            if (source === "fee") {
                var fee = parseAmount(feeInput.value);
                if (fee !== null && fee >= 0) {
                    invoiceInput.value = invoiceFromFee(fee, capConstants).toFixed(2);
                }
            } else {
                var invoice = parseAmount(invoiceInput.value);
                if (invoice !== null && invoice >= 0) {
                    feeInput.value = computeFee(invoice, capConstants).toFixed(2);
                }
            }
            syncing = false;
        }

        function syncCapEnabled() {
            var on = fieldset.querySelector('input[value="on"]').checked;
            invoiceInput.disabled = !on;
            feeInput.disabled = !on;
            if (!on) {
                invoiceInput.removeAttribute("required");
            } else {
                invoiceInput.setAttribute("required", "required");
                if (invoiceInput.value) {
                    syncCapInputs("invoice");
                }
            }
        }

        invoiceInput.addEventListener("input", function () {
            syncCapInputs("invoice");
        });
        feeInput.addEventListener("input", function () {
            syncCapInputs("fee");
        });
        feeInput.addEventListener("focus", function () {
            fieldset.querySelector('input[value="on"]').checked = true;
            syncCapEnabled();
        });
        invoiceInput.addEventListener("focus", function () {
            fieldset.querySelector('input[value="on"]').checked = true;
            syncCapEnabled();
        });
        radios.forEach(function (radio) {
            radio.addEventListener("change", syncCapEnabled);
        });

        syncCapEnabled();
        if (invoiceInput.value && !feeInput.value) {
            syncCapInputs("invoice");
        }
    }

    function initAll() {
        initAllFeeCalculators();
        initCapDualSync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
