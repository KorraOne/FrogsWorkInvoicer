(function () {
    "use strict";

    function syncAbnField() {
        var yes = document.querySelector('input.gst-registered-radio[value="yes"]');
        var abn = document.getElementById("business_abn");
        var label = document.getElementById("business_abn_label");
        if (!abn || !yes) {
            return;
        }
        var registered = yes.checked;
        abn.required = registered;
        if (label) {
            label.textContent = registered ? "Business ABN" : "Business ABN (optional)";
        }
    }

    document.querySelectorAll(".gst-registered-radio").forEach(function (radio) {
        radio.addEventListener("change", syncAbnField);
    });
    syncAbnField();
})();
