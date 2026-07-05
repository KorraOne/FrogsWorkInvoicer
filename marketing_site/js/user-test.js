(function () {
    var STORAGE_KEY = "frogswork-user-test-v3";
    var STEPS = [
        "intro",
        "part1",
        "scenario-a",
        "scenario-b",
        "scenario-c",
        "scenario-d",
        "scenario-e",
        "scenario-f",
        "feedback-1",
        "feedback-2",
        "uninstall",
        "submit",
        "success",
    ];

    var ANSWER_KEYS = [
        "getting_started",
        "invoice_workflow",
        "confidence_trust",
        "expectations_gaps",
        "overall",
        "pricing_trial",
        "anything_else",
    ];

    var FEEDBACK_1_KEYS = ["getting_started", "invoice_workflow", "confidence_trust"];
    var FEEDBACK_2_KEYS = ["expectations_gaps", "overall", "pricing_trial", "anything_else"];

    var API_BASE =
        window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
            ? "http://127.0.0.1:8787"
            : "https://api.frogswork.com";

    var state = {
        stepIndex: 0,
        intakeEnabled: false,
        maxBytes: 400 * 1024 * 1024,
        uninstallFailed: false,
        answers: {},
        testerName: "",
        submittedWithVideo: false,
    };

    var RETURN_BAR_STEPS = {
        part1: true,
        "scenario-a": true,
        "scenario-b": true,
        "scenario-c": true,
        "scenario-d": true,
        "scenario-e": true,
        "scenario-f": true,
    };

    var els = {
        progressLabel: document.getElementById("ut-progress-label"),
        progressFill: document.getElementById("ut-progress-fill"),
        closedBanner: document.getElementById("ut-closed"),
        returnBar: document.getElementById("ut-return-bar"),
        submitBtn: document.getElementById("ut-submit-btn"),
        submitError: document.getElementById("ut-submit-error"),
        uploadBox: document.getElementById("ut-upload-progress"),
        uploadStatus: document.getElementById("ut-upload-status"),
        uploadFill: document.getElementById("ut-upload-fill"),
        maxSizeHint: document.getElementById("ut-max-size-hint"),
        cleanup: document.getElementById("ut-cleanup"),
        successMessage: document.getElementById("ut-success-message"),
    };

    function loadState() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            var saved = JSON.parse(raw);
            if (typeof saved.stepIndex === "number") {
                state.stepIndex = Math.min(Math.max(0, saved.stepIndex), STEPS.length - 1);
            }
            if (saved.answers) state.answers = saved.answers;
            if (saved.testerName) state.testerName = saved.testerName;
            if (saved.uninstallFailed) state.uninstallFailed = saved.uninstallFailed;
        } catch (e) {
            /* ignore */
        }
    }

    function saveState() {
        collectAnswers();
        var nameEl = document.getElementById("ut-name");
        if (nameEl) state.testerName = nameEl.value;
        localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
                stepIndex: state.stepIndex,
                answers: state.answers,
                testerName: state.testerName,
                uninstallFailed: state.uninstallFailed,
            })
        );
    }

    function clearState() {
        localStorage.removeItem(STORAGE_KEY);
        state.stepIndex = 0;
        state.answers = {};
        state.testerName = "";
        state.uninstallFailed = false;
        state.submittedWithVideo = false;
    }

    function collectAnswers() {
        document.querySelectorAll("[data-answer]").forEach(function (el) {
            var key = el.getAttribute("data-answer");
            if (key) state.answers[key] = el.value;
        });
    }

    function applyAnswers() {
        document.querySelectorAll("[data-answer]").forEach(function (el) {
            var key = el.getAttribute("data-answer");
            if (key && state.answers[key]) el.value = state.answers[key];
        });
        var nameEl = document.getElementById("ut-name");
        if (nameEl && state.testerName) nameEl.value = state.testerName;
    }

    function showStep(index) {
        state.stepIndex = Math.min(Math.max(0, index), STEPS.length - 1);
        var current = STEPS[state.stepIndex];
        document.querySelectorAll(".user-test-step").forEach(function (section) {
            var isActive = section.getAttribute("data-step") === current;
            section.classList.toggle("hidden", !isActive);
            section.setAttribute("aria-hidden", isActive ? "false" : "true");
        });
        var pct = Math.round(((state.stepIndex + 1) / STEPS.length) * 100);
        if (els.progressLabel) {
            els.progressLabel.textContent =
                "Step " + (state.stepIndex + 1) + " of " + STEPS.length;
        }
        if (els.progressFill) {
            els.progressFill.style.width = pct + "%";
            els.progressFill.parentElement.setAttribute("aria-valuenow", String(pct));
        }
        if (current === "submit" && els.cleanup) {
            els.cleanup.classList.toggle("hidden", !state.uninstallFailed);
        }
        if (current === "success" && els.successMessage) {
            els.successMessage.textContent = state.submittedWithVideo
                ? "Your recording and answers were submitted successfully. You can close this page."
                : "Your answers were submitted successfully. You can close this page.";
        }
        if (els.returnBar) {
            els.returnBar.classList.toggle("hidden", !RETURN_BAR_STEPS[current]);
        }
        saveState();
        var active = document.querySelector(
            '.user-test-step[data-step="' + current + '"] h2, .user-test-step[data-step="' + current + '"] h1'
        );
        if (active) active.focus({ preventScroll: true });
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function nextStep() {
        if (state.stepIndex < STEPS.length - 1) showStep(state.stepIndex + 1);
    }

    function prevStep() {
        if (state.stepIndex > 0) showStep(state.stepIndex - 1);
    }

    function formatBytes(n) {
        if (n < 1024) return n + " B";
        if (n < 1024 * 1024) return Math.round(n / 1024) + " KB";
        return (n / (1024 * 1024)).toFixed(0) + " MB";
    }

    function fetchStatus() {
        return fetch(API_BASE + "/user-test/status", { method: "GET" })
            .then(function (res) {
                return res.json();
            })
            .then(function (data) {
                state.intakeEnabled = Boolean(data.enabled);
                if (data.maxBytes) state.maxBytes = data.maxBytes;
                if (els.closedBanner) {
                    els.closedBanner.classList.toggle("hidden", state.intakeEnabled);
                }
                if (els.submitBtn) {
                    els.submitBtn.disabled = !state.intakeEnabled;
                }
                if (els.maxSizeHint) {
                    els.maxSizeHint.textContent =
                        "Optional. Maximum file size: " + formatBytes(state.maxBytes) + ".";
                }
            })
            .catch(function () {
                if (els.closedBanner) {
                    els.closedBanner.textContent =
                        "Could not reach the server. You can read the steps, but submit may not work until you are online.";
                    els.closedBanner.classList.remove("hidden");
                }
            });
    }

    function validateAnswerKeys(keys) {
        collectAnswers();
        for (var i = 0; i < keys.length; i++) {
            if (!(state.answers[keys[i]] || "").trim()) {
                return false;
            }
        }
        return true;
    }

    function showFeedbackError(step, msg) {
        var el =
            step === "feedback-1"
                ? document.getElementById("ut-feedback-1-error")
                : step === "feedback-2"
                  ? document.getElementById("ut-feedback-2-error")
                  : null;
        if (!el) return;
        if (!msg) {
            el.classList.add("hidden");
            el.textContent = "";
        } else {
            el.textContent = msg;
            el.classList.remove("hidden");
        }
    }

    function activeStepSection() {
        var current = STEPS[state.stepIndex];
        return document.querySelector('.user-test-step[data-step="' + current + '"]');
    }

    function requireStepConfirm() {
        var section = activeStepSection();
        if (!section) {
            return true;
        }
        var checkbox = section.querySelector("[data-step-confirm]");
        if (!checkbox) {
            return true;
        }
        var errorEl =
            section.querySelector("[data-step-error]") ||
            document.getElementById("ut-part1-error");
        if (!checkbox.checked) {
            if (errorEl) {
                errorEl.textContent =
                    "Tick the box when you have finished in FrogsWork and come back to this page.";
                errorEl.classList.remove("hidden");
            }
            return false;
        }
        if (errorEl) {
            errorEl.textContent = "";
            errorEl.classList.add("hidden");
        }
        return true;
    }

    function tryNextStep() {
        var current = STEPS[state.stepIndex];
        var feedbackMsg =
            "Fill in every box. If something does not apply, write None.";
        if (RETURN_BAR_STEPS[current] && !requireStepConfirm()) {
            return;
        }
        if (current === "feedback-1") {
            if (!validateAnswerKeys(FEEDBACK_1_KEYS)) {
                showFeedbackError("feedback-1", feedbackMsg);
                return;
            }
            showFeedbackError("feedback-1", "");
        }
        if (current === "feedback-2") {
            if (!validateAnswerKeys(FEEDBACK_2_KEYS)) {
                showFeedbackError("feedback-2", feedbackMsg);
                return;
            }
            showFeedbackError("feedback-2", "");
        }
        nextStep();
    }

    function buildAnswersPayload() {
        collectAnswers();
        var payload = {
            tester_name: (document.getElementById("ut-name") || {}).value || "",
            website: (document.getElementById("ut-website") || {}).value || "",
        };
        for (var i = 0; i < ANSWER_KEYS.length; i++) {
            var key = ANSWER_KEYS[i];
            payload[key] = state.answers[key] || "";
        }
        return payload;
    }

    function copyAnswers() {
        collectAnswers();
        var labels = {
            getting_started: "Getting started",
            invoice_workflow: "Invoices",
            confidence_trust: "Confidence",
            expectations_gaps: "Expectations",
            overall: "Overall",
            pricing_trial: "Pricing and trial",
            anything_else: "Anything else",
        };
        var text = "FrogsWork user test answers\n";
        for (var i = 0; i < ANSWER_KEYS.length; i++) {
            var key = ANSWER_KEYS[i];
            text += "\n" + labels[key] + ":\n" + (state.answers[key] || "") + "\n";
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                alert("Answers copied to clipboard.");
            });
        } else {
            prompt("Copy your answers:", text);
        }
    }

    function uploadWithProgress(url, file, headers, onProgress) {
        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open("PUT", url);
            Object.keys(headers || {}).forEach(function (k) {
                xhr.setRequestHeader(k, headers[k]);
            });
            xhr.upload.onprogress = function (ev) {
                if (ev.lengthComputable && onProgress) {
                    onProgress(ev.loaded / ev.total);
                }
            };
            xhr.onload = function () {
                if (xhr.status >= 200 && xhr.status < 300) resolve();
                else reject(new Error("Upload failed (" + xhr.status + ")."));
            };
            xhr.onerror = function () {
                reject(new Error("Upload failed. Check your connection."));
            };
            xhr.send(file);
        });
    }

    function completeSubmission(submissionId, payload) {
        return fetch(API_BASE + "/user-test/submissions/" + submissionId + "/complete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
    }

    function submitResults() {
        if (!state.intakeEnabled) {
            showError("Submissions are closed right now.");
            return;
        }
        var fileInput = document.getElementById("ut-video");
        var file = fileInput && fileInput.files && fileInput.files[0];
        var payload = buildAnswersPayload();
        for (var i = 0; i < ANSWER_KEYS.length; i++) {
            if (!payload[ANSWER_KEYS[i]].trim()) {
                showError(
                    "Fill in every feedback box (go back to Feedback). If something does not apply, write None."
                );
                return;
            }
        }
        if (file) {
            if (!file.type.startsWith("video/")) {
                showError("Please select a video file.");
                return;
            }
            if (file.size > state.maxBytes) {
                showError("Video is too large. Maximum is " + formatBytes(state.maxBytes) + ".");
                return;
            }
        }

        if (els.submitBtn) els.submitBtn.disabled = true;
        showError("");

        var createBody = { website: payload.website };
        if (file) {
            createBody.contentType = file.type;
            createBody.contentLength = file.size;
        } else {
            createBody.hasVideo = false;
        }

        var chain;
        if (file) {
            if (els.uploadBox) els.uploadBox.classList.remove("hidden");
            chain = fetch(API_BASE + "/user-test/submissions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(createBody),
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result.ok) {
                        throw new Error(result.data.error || "Could not start upload.");
                    }
                    var data = result.data;
                    if (els.uploadStatus) els.uploadStatus.textContent = "Uploading video…";
                    return uploadWithProgress(
                        data.uploadUrl,
                        file,
                        data.uploadHeaders,
                        function (pct) {
                            if (els.uploadFill) {
                                els.uploadFill.style.width = Math.round(pct * 100) + "%";
                            }
                        }
                    ).then(function () {
                        if (els.uploadStatus) els.uploadStatus.textContent = "Saving answers…";
                        return completeSubmission(data.submissionId, payload);
                    });
                });
        } else {
            if (els.uploadStatus) els.uploadStatus.textContent = "Saving answers…";
            if (els.uploadBox) els.uploadBox.classList.remove("hidden");
            chain = fetch(API_BASE + "/user-test/submissions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(createBody),
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result.ok) {
                        throw new Error(result.data.error || "Could not start submission.");
                    }
                    return completeSubmission(result.data.submissionId, payload);
                });
        }

        chain
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok) throw new Error(data.error || "Submit failed.");
                    var hadVideo = Boolean(file);
                    clearState();
                    state.submittedWithVideo = hadVideo;
                    showStep(STEPS.indexOf("success"));
                });
            })
            .catch(function (err) {
                showError(err.message || "Submit failed.");
                if (els.submitBtn) els.submitBtn.disabled = !state.intakeEnabled;
            })
            .finally(function () {
                if (els.uploadBox) els.uploadBox.classList.add("hidden");
            });
    }

    function showError(msg) {
        if (!els.submitError) return;
        if (!msg) {
            els.submitError.classList.add("hidden");
            els.submitError.textContent = "";
        } else {
            els.submitError.textContent = msg;
            els.submitError.classList.remove("hidden");
        }
    }

    function onClick(ev) {
        var btn = ev.target.closest("[data-action]");
        if (!btn) return;
        var action = btn.getAttribute("data-action");
        if (action === "next") tryNextStep();
        if (action === "back") prevStep();
        if (action === "part1-done") {
            if (requireStepConfirm()) nextStep();
        }
        if (action === "uninstall-ok") {
            state.uninstallFailed = false;
            nextStep();
        }
        if (action === "uninstall-fail") {
            state.uninstallFailed = true;
            nextStep();
        }
        if (action === "submit") submitResults();
        if (action === "copy-answers") copyAnswers();
        if (action === "reset") {
            clearState();
            applyAnswers();
            fetchStatus().then(function () {
                showStep(0);
            });
        }
    }

    function onInput(ev) {
        if (ev.target.matches("[data-answer], #ut-name")) {
            saveState();
        }
    }

    loadState();
    applyAnswers();
    document.getElementById("user-test-app").addEventListener("click", onClick);
    document.getElementById("user-test-app").addEventListener("input", onInput);

    fetchStatus().then(function () {
        if (STEPS[state.stepIndex] === "success") {
            showStep(0);
        } else {
            showStep(state.stepIndex);
        }
    });
})();
