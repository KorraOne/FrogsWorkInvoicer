/**
 * Light GA4 helper for the marketing site.
 * Loads gtag only when FW_GA4_MARKETING_ID is set. Never send emails or PII.
 *
 * Custom events (conversions: mark only `purchase` as a key event in GA4 Admin):
 *   signup_click, sign_up, begin_checkout, purchase,
 *   open_app_click, download_click, video_play, video_progress, support_contact_click
 */
(function () {
  var id = String(window.FW_GA4_MARKETING_ID || "").trim();

  function track(eventName, params) {
    if (!window.gtag || !eventName) return;
    var safe = {};
    if (params && typeof params === "object") {
      Object.keys(params).forEach(function (key) {
        var val = params[key];
        if (val == null) return;
        if (typeof val === "string" || typeof val === "number" || typeof val === "boolean") {
          safe[key] = val;
        }
      });
    }
    window.gtag("event", eventName, safe);
  }

  window.fwGa = {
    track: track,
    signupClick: function (page) {
      track("signup_click", { page: page || "other" });
    },
    openAppClick: function (location) {
      track("open_app_click", { location: location || "other" });
    },
    downloadClick: function (location) {
      track("download_click", { platform: "windows", location: location || "other" });
    },
    supportContactClick: function () {
      track("support_contact_click", { method: "mailto" });
    },
    videoPlay: function (videoId) {
      track("video_play", { video_id: videoId || "unknown" });
    },
    videoProgress: function (videoId, percent) {
      track("video_progress", { video_id: videoId || "unknown", percent: percent });
    },
    ctaClick: function (ctaId, page) {
      track("cta_click", { cta_id: ctaId || "unknown", page: page || location.pathname });
    },
  };

  if (!id || id.indexOf("G-") !== 0) {
    return;
  }

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", id, { anonymize_ip: true, send_page_view: true });

  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
  document.head.appendChild(s);

  document.addEventListener("click", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("a, button, [data-fw-signup], [data-fw-open-app], [data-fw-download], [data-fw-support], [data-fw-cta]") : null;
    if (!el) return;

    if (el.hasAttribute("data-fw-signup")) {
      window.fwGa.signupClick(el.getAttribute("data-fw-signup") || "other");
      return;
    }
    if (el.hasAttribute("data-fw-open-app")) {
      window.fwGa.openAppClick(el.getAttribute("data-fw-open-app") || "other");
      return;
    }
    if (el.hasAttribute("data-fw-download")) {
      window.fwGa.downloadClick(el.getAttribute("data-fw-download") || "other");
      return;
    }
    if (el.hasAttribute("data-fw-support")) {
      window.fwGa.supportContactClick();
      return;
    }
    if (el.hasAttribute("data-fw-cta")) {
      window.fwGa.ctaClick(el.getAttribute("data-fw-cta") || "cta", location.pathname);
    }
  });
})();
