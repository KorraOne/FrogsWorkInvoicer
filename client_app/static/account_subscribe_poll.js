(function () {
    var configEl = document.getElementById("account-subscribe-config");
    if (!configEl) return;
    var config = JSON.parse(configEl.textContent || "{}");
    var statusUrl = config.statusUrl;
    if (!statusUrl) return;

    function poll() {
        fetch(statusUrl, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ready && data.redirect) {
                    window.location.href = data.redirect;
                    return;
                }
                setTimeout(poll, 1500);
            })
            .catch(function () { setTimeout(poll, 3000); });
    }
    setTimeout(poll, 1500);
})();
