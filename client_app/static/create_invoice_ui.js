(function () {
    var addBtn = document.getElementById("add-item-btn");
    var container = document.getElementById("items");
    var invoiceForm = document.getElementById("invoice-form");
    var addCustomerForm = document.getElementById("add-customer-form");
    var draftFields = document.getElementById("add-customer-draft-fields");
    if (!addBtn || !container || !invoiceForm || !addCustomerForm || !draftFields) {
        return;
    }

    function formatPreview(desc, qty, amount) {
        desc = (desc || "").trim();
        qty = (qty || "1").trim() || "1";
        amount = (amount || "").trim();
        if (!desc && !amount) {
            return "Not filled in yet";
        }
        var text = desc || "No description";
        if (amount) {
            text += " · " + qty + " × $" + amount.replace(/^\$/, "");
        }
        return text;
    }

    function updateLineItemPreview(row) {
        var desc = row.querySelector(".item-description-input");
        var qty = row.querySelector(".item-quantity-input");
        var amount = row.querySelector(".item-amount-input");
        var preview = row.querySelector(".line-item-preview");
        if (preview) {
            preview.textContent = formatPreview(
                desc ? desc.value : "",
                qty ? qty.value : "",
                amount ? amount.value : ""
            );
        }
    }

    function renumberLineItems() {
        var rows = container.querySelectorAll(".line-item");
        rows.forEach(function (row, index) {
            var number = row.querySelector(".line-item-number");
            if (number) {
                number.textContent = "Line item " + (index + 1);
            }
        });
    }

    function updateRemoveButtons() {
        var rows = container.querySelectorAll(".line-item");
        var showRemove = rows.length > 1;
        rows.forEach(function (row) {
            var btn = row.querySelector(".item-remove-btn");
            if (btn) {
                btn.hidden = !showRemove;
            }
        });
    }

    function syncGstHidden(row) {
        var cb = row.querySelector(".item-gst-applicable-input");
        var hidden = row.querySelector(".item-gst-free-hidden");
        var label = row.querySelector(".gst-mode-label");
        if (cb && hidden) {
            hidden.value = cb.checked ? "" : "on";
            row.classList.toggle("line-item--gst-applicable", cb.checked);
            if (label) {
                label.textContent = cb.checked ? "GST applicable" : "GST-free";
            }
        }
    }

    function bindLineItem(row) {
        row.querySelectorAll(".item-description-input, .item-quantity-input, .item-amount-input").forEach(function (input) {
            input.addEventListener("input", function () {
                updateLineItemPreview(row);
            });
        });
        var gstControl = row.querySelector(".line-item-gst-control");
        if (gstControl) {
            gstControl.addEventListener("click", function (event) {
                event.stopPropagation();
            });
            var gstCheckbox = row.querySelector(".item-gst-applicable-input");
            if (gstCheckbox) {
                gstCheckbox.addEventListener("change", function () {
                    syncGstHidden(row);
                });
                syncGstHidden(row);
            }
        }
        updateLineItemPreview(row);
    }

    addBtn.addEventListener("click", function () {
        var template = container.querySelector(".line-item");
        var row = template.cloneNode(true);
        row.open = true;
        row.querySelectorAll("input").forEach(function (input) {
            if (input.classList.contains("item-quantity-input")) {
                input.value = "1";
            } else if (input.classList.contains("item-gst-free-hidden")) {
                input.value = "";
            } else if (input.classList.contains("item-gst-applicable-input")) {
                input.checked = true;
            } else if (input.type === "checkbox") {
                input.checked = false;
            } else {
                input.value = "";
            }
        });
        row.classList.add("line-item--gst-applicable");
        container.appendChild(row);
        bindLineItem(row);
        renumberLineItems();
        updateRemoveButtons();
        row.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    container.addEventListener("click", function (event) {
        var btn = event.target.closest(".item-remove-btn");
        if (!btn) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (container.querySelectorAll(".line-item").length <= 1) {
            return;
        }
        btn.closest(".line-item").remove();
        renumberLineItems();
        updateRemoveButtons();
    });

    container.querySelectorAll(".line-item").forEach(bindLineItem);

    addCustomerForm.addEventListener("submit", function () {
        draftFields.innerHTML = "";
        invoiceForm.querySelectorAll("input, select, textarea").forEach(function (field) {
            if (!field.name || field.disabled) {
                return;
            }
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = field.name;
            input.value = field.value;
            draftFields.appendChild(input);
        });
    });

    renumberLineItems();
    updateRemoveButtons();

    var numberDisplay = document.getElementById("invoice-number-display");
    var numberForm = document.getElementById("invoice-number-form");
    var numberValue = document.getElementById("invoice-number-value");
    var numberInput = document.getElementById("invoice_number_input");
    var numberHidden = document.getElementById("invoice_number");
    var changeBtn = document.getElementById("invoice-number-change-btn");
    var saveBtn = document.getElementById("invoice-number-save-btn");
    var cancelBtn = document.getElementById("invoice-number-cancel-btn");

    function padInvoiceNumber(value) {
        var digits = String(value || "").replace(/\D/g, "");
        if (!digits) {
            return "";
        }
        return digits.padStart(8, "0");
    }

    function showNumberDisplay() {
        if (!numberDisplay || !numberForm) {
            return;
        }
        numberDisplay.hidden = false;
        numberForm.hidden = true;
    }

    function showNumberEdit() {
        if (!numberDisplay || !numberForm || !numberInput || !numberHidden) {
            return;
        }
        numberInput.value = numberHidden.value;
        numberDisplay.hidden = true;
        numberForm.hidden = false;
        numberInput.focus();
        numberInput.select();
    }

    if (changeBtn) {
        changeBtn.addEventListener("click", showNumberEdit);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener("click", showNumberDisplay);
    }
    if (saveBtn) {
        saveBtn.addEventListener("click", function () {
            var raw = parseInt(numberInput.value, 10);
            if (!raw || raw < 1) {
                return;
            }
            numberHidden.value = String(raw);
            if (numberValue) {
                numberValue.textContent = padInvoiceNumber(raw);
            }
            showNumberDisplay();
        });
    }
})();
