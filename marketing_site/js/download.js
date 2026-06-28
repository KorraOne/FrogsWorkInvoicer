(function () {
    var versionEl = document.getElementById("release-version");
    var notesEl = document.getElementById("release-notes");
    var shaEl = document.getElementById("release-sha256");
    var btn = document.getElementById("download-btn");
    var fallback = document.getElementById("download-fallback");

    if (!btn) {
        return;
    }

    fetch("/releases.json", { cache: "no-store" })
        .then(function (resp) {
            if (!resp.ok) {
                throw new Error("No release manifest");
            }
            return resp.json();
        })
        .then(function (data) {
            if (!data.version || !data.download_path) {
                throw new Error("Incomplete manifest");
            }
            if (versionEl) {
                versionEl.textContent = data.version;
            }
            if (notesEl && data.notes) {
                notesEl.textContent = data.notes;
                notesEl.hidden = false;
            }
            if (shaEl && data.sha256) {
                shaEl.textContent = data.sha256;
                shaEl.parentElement.hidden = false;
            }
            btn.href = data.download_path;
            btn.removeAttribute("aria-disabled");
            if (fallback) {
                fallback.hidden = true;
            }
        })
        .catch(function () {
            if (fallback) {
                fallback.hidden = false;
            }
            btn.setAttribute("aria-disabled", "true");
            btn.classList.add("btn-secondary");
            btn.classList.remove("btn-primary");
            btn.textContent = "Release not published yet";
            btn.removeAttribute("href");
        });
})();
