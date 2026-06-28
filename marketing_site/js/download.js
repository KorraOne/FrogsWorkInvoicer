(function () {
    var versionEl = document.getElementById("release-version");
    var btn = document.getElementById("download-btn");
    var fallback = document.getElementById("download-fallback");
    var historyList = document.getElementById("version-history-list");
    var historyDetails = document.getElementById("version-history");

    if (!btn) {
        return;
    }

    function formatDate(isoDate) {
        if (!isoDate) {
            return "";
        }
        var parts = isoDate.split("-");
        if (parts.length !== 3) {
            return isoDate;
        }
        var months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ];
        var month = parseInt(parts[1], 10);
        if (month < 1 || month > 12) {
            return isoDate;
        }
        return months[month - 1] + " " + parseInt(parts[2], 10) + ", " + parts[0];
    }

    function buildHistory(data) {
        if (Array.isArray(data.history) && data.history.length) {
            return data.history.slice();
        }
        if (data.version) {
            return [{
                version: data.version,
                published_at: data.published_at || "",
                notes: data.notes || ""
            }];
        }
        return [];
    }

    function renderHistory(data) {
        if (!historyList) {
            return;
        }
        var entries = buildHistory(data);
        if (!entries.length) {
            if (historyDetails) {
                historyDetails.hidden = true;
            }
            return;
        }
        historyList.innerHTML = "";
        entries.forEach(function (entry) {
            var item = document.createElement("li");
            item.className = "version-history-item";

            var heading = document.createElement("p");
            heading.className = "version-history-heading";
            var versionLabel = document.createElement("strong");
            versionLabel.textContent = "Version " + entry.version;
            heading.appendChild(versionLabel);
            if (entry.published_at) {
                var date = document.createElement("span");
                date.className = "version-history-date";
                date.textContent = formatDate(entry.published_at);
                heading.appendChild(date);
            }
            item.appendChild(heading);

            if (entry.notes) {
                var notes = document.createElement("p");
                notes.className = "version-history-notes";
                notes.textContent = entry.notes;
                item.appendChild(notes);
            }

            historyList.appendChild(item);
        });
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
            renderHistory(data);
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
            if (historyDetails) {
                historyDetails.hidden = true;
            }
            btn.setAttribute("aria-disabled", "true");
            btn.classList.add("btn-secondary");
            btn.classList.remove("btn-primary");
            btn.textContent = "Release not published yet";
            btn.removeAttribute("href");
        });
})();
