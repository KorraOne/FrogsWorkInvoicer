(function () {
    var form = document.querySelector("form[data-unsaved-guard]");
    if (!form) {
        return;
    }

    var dirty = false;
    var submitting = false;

    function markDirty() {
        if (!submitting) {
            dirty = true;
        }
    }

    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);

    var logoGroup = form.querySelector(".logo-fields-group");
    if (logoGroup) {
        logoGroup.addEventListener("pointerup", markDirty);
        logoGroup.addEventListener("change", markDirty);
    }

    form.addEventListener("submit", function () {
        submitting = true;
        dirty = false;
    });

    window.addEventListener("beforeunload", function (event) {
        if (!dirty || submitting) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });

    document.addEventListener("click", function (event) {
        if (!dirty || submitting) {
            return;
        }
        var link = event.target.closest("a[href]");
        if (!link) {
            return;
        }
        var href = link.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") {
            return;
        }
        if (link.target === "_blank" || link.hasAttribute("download")) {
            return;
        }
        if (!window.confirm("You have unsaved changes. Leave without saving?")) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);
})();
