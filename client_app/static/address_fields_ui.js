(function () {
    "use strict";

    function collapseSpaces(value) {
        return String(value || "").trim().replace(/\s+/g, " ");
    }

    function titleCaseWords(value) {
        var text = collapseSpaces(value);
        if (!text) {
            return "";
        }
        return text.replace(/\b([A-Za-z])([A-Za-z']*)/g, function (_, first, rest) {
            return first.toUpperCase() + rest.toLowerCase();
        });
    }

    function compactPostcode(value) {
        return String(value || "").replace(/\D/g, "").slice(0, 4);
    }

    function bindAddressGroup(group) {
        if (group.getAttribute("data-address-ui") === "1") {
            return;
        }
        group.setAttribute("data-address-ui", "1");

        group.querySelectorAll(".address-line-input").forEach(function (input) {
            input.addEventListener("blur", function () {
                input.value = collapseSpaces(input.value);
            });
        });

        group.querySelectorAll(".address-suburb-input").forEach(function (input) {
            input.addEventListener("blur", function () {
                input.value = titleCaseWords(input.value);
            });
        });

        group.querySelectorAll(".address-postcode-input").forEach(function (input) {
            input.addEventListener("input", function () {
                var next = compactPostcode(input.value);
                if (input.value !== next) {
                    input.value = next;
                }
            });
            input.addEventListener("blur", function () {
                input.value = compactPostcode(input.value);
            });
        });
    }

    window.initAddressFieldsUi = function (root) {
        var scope = root || document;
        scope.querySelectorAll(".address-fields-group").forEach(bindAddressGroup);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            window.initAddressFieldsUi();
        });
    } else {
        window.initAddressFieldsUi();
    }
})();
