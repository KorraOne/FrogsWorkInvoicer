(function () {
    "use strict";

    var CATEGORY_LABELS = {
        install: "Install",
        "getting-started": "Getting started",
        invoicing: "Invoicing",
        quotes: "Quotes",
        dashboard: "Dashboard",
        subscription: "Subscription and sign-in",
        windows: "Windows desktop"
    };

    var CATEGORY_ORDER = [
        "install",
        "getting-started",
        "invoicing",
        "quotes",
        "dashboard",
        "subscription",
        "windows"
    ];

    var DEVICE_LABELS = {
        iphone: "Tutorial recorded on iPhone",
        android: "Tutorial recorded on Android",
        desktop: "Tutorial recorded on Windows"
    };

    function formatDuration(seconds) {
        var s = Math.max(0, parseInt(seconds, 10) || 0);
        if (s >= 60) {
            var m = Math.floor(s / 60);
            var r = s % 60;
            return m + ":" + String(r).padStart(2, "0");
        }
        return "0:" + String(s).padStart(2, "0");
    }

    function formatDurationLabel(seconds) {
        var s = parseInt(seconds, 10) || 0;
        if (s >= 60) {
            var m = Math.floor(s / 60);
            var r = s % 60;
            if (r === 0) {
                return m + " min";
            }
            return m + " min " + r + " sec";
        }
        return s + " sec";
    }

    function isNonEmptyString(v) {
        return typeof v === "string" && v.trim().length > 0;
    }

    function isPublishableTutorial(entry) {
        if (!entry || entry.published !== true) {
            return false;
        }
        if (!isNonEmptyString(entry.id) || !isNonEmptyString(entry.title)) {
            return false;
        }
        if (!isNonEmptyString(entry.category) || !isNonEmptyString(entry.file)) {
            return false;
        }
        if (!isNonEmptyString(entry.poster)) {
            return false;
        }
        if (!entry.duration_seconds && entry.duration_seconds !== 0) {
            return false;
        }
        if (!Array.isArray(entry.steps) || entry.steps.length < 1) {
            return false;
        }
        return entry.steps.some(function (step) {
            return isNonEmptyString(step);
        });
    }

    function isPublishableWalkthrough(entry) {
        if (!entry || entry.published !== true) {
            return false;
        }
        return (
            isNonEmptyString(entry.id) &&
            isNonEmptyString(entry.title) &&
            isNonEmptyString(entry.file) &&
            isNonEmptyString(entry.poster) &&
            (entry.duration_seconds || entry.duration_seconds === 0)
        );
    }

    function mediaUrl(manifest, relativePath) {
        var base = (manifest.cdn_base || "").replace(/\/$/, "");
        var path = (relativePath || "").replace(/^\//, "");
        return base + "/" + path;
    }

    var VIDEO_PROGRESS_MARKS = [25, 50, 75, 100];

    function attachVideoAnalytics(video, videoId) {
        if (!video || !videoId) {
            return;
        }
        var played = false;
        var fired = {};

        video.addEventListener("play", function () {
            if (played) {
                return;
            }
            played = true;
            if (window.fwGa && typeof window.fwGa.videoPlay === "function") {
                window.fwGa.videoPlay(videoId);
            }
        });

        video.addEventListener("timeupdate", function () {
            var duration = video.duration;
            if (!duration || !isFinite(duration) || duration <= 0) {
                return;
            }
            var pct = (video.currentTime / duration) * 100;
            VIDEO_PROGRESS_MARKS.forEach(function (mark) {
                if (pct >= mark && !fired[mark]) {
                    fired[mark] = true;
                    if (window.fwGa && typeof window.fwGa.videoProgress === "function") {
                        window.fwGa.videoProgress(videoId, mark);
                    }
                }
            });
        });
    }

    function buildVideoElement(manifest, entry, className) {
        var wrap = document.createElement("div");
        wrap.className = className || "video-player-wrap";

        if (!isPublishableTutorial(entry) && !isPublishableWalkthrough(entry)) {
            var soon = document.createElement("div");
            soon.className = "video-coming-soon";
            soon.textContent = "Video coming soon";
            wrap.appendChild(soon);
            return wrap;
        }

        var video = document.createElement("video");
        video.className = "video-player";
        video.controls = true;
        video.playsInline = true;
        video.preload = "metadata";
        video.poster = mediaUrl(manifest, entry.poster);
        video.src = mediaUrl(manifest, entry.file);
        attachVideoAnalytics(video, entry.id);
        wrap.appendChild(video);
        return wrap;
    }

    function buildStepsList(steps) {
        var ol = document.createElement("ol");
        ol.className = "tutorial-steps";
        (steps || []).forEach(function (step) {
            if (!isNonEmptyString(step)) {
                return;
            }
            var li = document.createElement("li");
            li.textContent = step;
            ol.appendChild(li);
        });
        return ol;
    }

    function findTutorial(manifest, id) {
        return (manifest.tutorials || []).find(function (t) {
            return t.id === id;
        });
    }

    function renderWalkthrough(manifest) {
        var root = document.getElementById("guides-walkthrough");
        if (!root) {
            return;
        }
        var wt = manifest.walkthrough;
        if (!wt) {
            return;
        }

        root.innerHTML = "";
        var title = document.createElement("h2");
        title.className = "section-heading";
        title.id = wt.id;
        title.textContent = wt.title;
        root.appendChild(title);

        if (wt.duration_seconds) {
            var meta = document.createElement("p");
            meta.className = "video-player-meta";
            meta.textContent = "Length: " + formatDurationLabel(wt.duration_seconds);
            root.appendChild(meta);
        }

        if (Array.isArray(wt.summary) && wt.summary.length) {
            var ul = document.createElement("ul");
            ul.className = "walkthrough-summary";
            wt.summary.forEach(function (item) {
                var li = document.createElement("li");
                li.textContent = item;
                ul.appendChild(li);
            });
            root.appendChild(ul);
        }

        root.appendChild(buildVideoElement(manifest, wt, "video-player-wrap"));
    }

    function renderTutorialCard(manifest, tutorial) {
        var card = document.createElement("article");
        card.className = "tutorial-card";
        card.id = tutorial.id;

        var head = document.createElement("div");
        head.className = "tutorial-card-head";

        var h3 = document.createElement("h3");
        h3.textContent = tutorial.title;
        head.appendChild(h3);

        if (tutorial.duration_seconds) {
            var dur = document.createElement("span");
            dur.className = "tutorial-duration";
            dur.textContent = formatDuration(tutorial.duration_seconds);
            head.appendChild(dur);
        }

        if (tutorial.device && DEVICE_LABELS[tutorial.device]) {
            var device = document.createElement("p");
            device.className = "tutorial-device";
            device.textContent = DEVICE_LABELS[tutorial.device];
            head.appendChild(device);
        }

        card.appendChild(head);

        if (Array.isArray(tutorial.steps) && tutorial.steps.length) {
            card.appendChild(buildStepsList(tutorial.steps));
        }

        var playerHost = document.createElement("div");
        playerHost.className = "tutorial-player-host";
        if (isPublishableTutorial(tutorial)) {
            playerHost.appendChild(buildVideoElement(manifest, tutorial, ""));
        } else {
            var soon = document.createElement("div");
            soon.className = "video-coming-soon";
            soon.textContent = "Video coming soon";
            playerHost.appendChild(soon);
        }
        card.appendChild(playerHost);

        return card;
    }

    function renderTutorialGrid(manifest) {
        var root = document.getElementById("guides-tutorials");
        if (!root) {
            return;
        }
        root.innerHTML = "";

        var nav = document.getElementById("guides-category-nav");
        if (nav) {
            nav.innerHTML = "";
            CATEGORY_ORDER.forEach(function (cat) {
                var a = document.createElement("a");
                a.href = "#guides-cat-" + cat;
                a.textContent = CATEGORY_LABELS[cat] || cat;
                nav.appendChild(a);
            });
        }

        var byCategory = {};
        (manifest.tutorials || []).forEach(function (t) {
            var cat = t.category || "data";
            if (!byCategory[cat]) {
                byCategory[cat] = [];
            }
            byCategory[cat].push(t);
        });

        CATEGORY_ORDER.forEach(function (cat) {
            var items = byCategory[cat];
            if (!items || !items.length) {
                return;
            }
            var section = document.createElement("section");
            section.className = "guides-category";
            section.id = "guides-cat-" + cat;

            var h2 = document.createElement("h2");
            h2.textContent = CATEGORY_LABELS[cat] || cat;
            section.appendChild(h2);

            var grid = document.createElement("div");
            grid.className = "tutorial-grid";
            items.forEach(function (tutorial) {
                grid.appendChild(renderTutorialCard(manifest, tutorial));
            });
            section.appendChild(grid);
            root.appendChild(section);
        });
    }

    function renderInlinePlayers(manifest) {
        document.querySelectorAll(".guide-inline[data-guide-id]").forEach(function (el) {
            var id = el.getAttribute("data-guide-id");
            var tutorial = findTutorial(manifest, id);
            if (!tutorial) {
                return;
            }
            el.innerHTML = "";
            if (!isPublishableTutorial(tutorial)) {
                el.hidden = true;
                return;
            }
            el.hidden = false;

            var h3 = document.createElement("h3");
            h3.textContent =
                tutorial.title +
                (tutorial.duration_seconds
                    ? " (" + formatDurationLabel(tutorial.duration_seconds) + ")"
                    : "");
            el.appendChild(h3);

            el.appendChild(buildVideoElement(manifest, tutorial, ""));
        });
    }

    function renderGuideLinks(manifest) {
        document.querySelectorAll("[data-guide-link]").forEach(function (el) {
            var id = el.getAttribute("data-guide-link");
            var tutorial = findTutorial(manifest, id);
            if (!tutorial) {
                return;
            }
            var dur = tutorial.duration_seconds
                ? " (" + formatDurationLabel(tutorial.duration_seconds) + ")"
                : "";
            var label = el.getAttribute("data-guide-label") || tutorial.title;
            el.innerHTML =
                '<a href="/guides.html#' +
                encodeURIComponent(id) +
                '">Watch: ' +
                label +
                dur +
                "</a>";
        });
    }

    function scrollToHash() {
        var hash = window.location.hash.replace(/^#/, "");
        if (!hash) {
            return;
        }
        var target = document.getElementById(hash);
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function initHeroScreenshot() {
        var link = document.querySelector(".hero-screenshot-link");
        if (!link) {
            return;
        }
        var img = link.querySelector(".hero-screenshot");
        if (img) {
            img.addEventListener("error", function () {
                link.classList.add("is-placeholder");
            });
            if (!img.complete || img.naturalWidth === 0) {
                if (img.complete) {
                    link.classList.add("is-placeholder");
                }
            }
        }
    }

    function init() {
        initHeroScreenshot();

        fetch("/videos.json")
            .then(function (res) {
                if (!res.ok) {
                    throw new Error("videos.json");
                }
                return res.json();
            })
            .then(function (manifest) {
                window.FrogsWorkVideos = manifest;
                renderWalkthrough(manifest);
                renderTutorialGrid(manifest);
                renderInlinePlayers(manifest);
                renderGuideLinks(manifest);
                scrollToHash();
            })
            .catch(function () {
                var root = document.getElementById("guides-tutorials");
                if (root) {
                    root.innerHTML =
                        '<p class="section-lead">Video guides are not available right now. Try again later or <a href="/support.html">contact support</a>.</p>';
                }
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
