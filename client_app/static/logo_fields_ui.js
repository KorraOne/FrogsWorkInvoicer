(function () {
    "use strict";

    var MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
    var MIN_DIMENSION = 32;
    var SLOT_PADDING_PX = 4;
    var MIN_SLOT_HEIGHT_PX = 48;

    function clamp(value, low, high) {
        return Math.max(low, Math.min(high, value));
    }

    function parseConfig() {
        var el = document.getElementById("logo-editor-config");
        if (!el) {
            return {};
        }
        try {
            return JSON.parse(el.textContent || "{}");
        } catch (err) {
            return {};
        }
    }

    function parsePlacement(editor) {
        var scaleEl = document.getElementById("logo_placement_scale");
        var oxEl = document.getElementById("logo_placement_offset_x");
        var oyEl = document.getElementById("logo_placement_offset_y");
        return {
            scale: parseFloat(scaleEl && scaleEl.value) || 1,
            offset_x: parseFloat(oxEl && oxEl.value) || 0,
            offset_y: parseFloat(oyEl && oyEl.value) || 0,
        };
    }

    function writePlacement(placement) {
        var scaleEl = document.getElementById("logo_placement_scale");
        var oxEl = document.getElementById("logo_placement_offset_x");
        var oyEl = document.getElementById("logo_placement_offset_y");
        if (scaleEl) {
            scaleEl.value = String(placement.scale);
        }
        if (oxEl) {
            oxEl.value = String(placement.offset_x);
        }
        if (oyEl) {
            oyEl.value = String(placement.offset_y);
        }
    }

    function computeLayout(naturalW, naturalH, frameW, frameH, placement) {
        var base = Math.min(frameW / naturalW, frameH / naturalH);
        var scale = base * placement.scale;
        var width = naturalW * scale;
        var height = naturalH * scale;
        var left = (frameW - width) / 2 + placement.offset_x * frameW;
        var top = (frameH - height) / 2 + placement.offset_y * frameH;
        return { width: width, height: height, left: left, top: top };
    }

    function bindEditor(group) {
        if (group.getAttribute("data-logo-ui-bound") === "1") {
            return;
        }
        group.setAttribute("data-logo-ui-bound", "1");

        var config = parseConfig();
        var scaleMin = config.scaleMin || 0.5;
        var scaleMax = config.scaleMax || 3;
        var canvasW = config.canvasWidth || 900;
        var canvasH = config.canvasHeight || 500;
        var editor = group.querySelector(".logo-placement-editor");
        if (!editor) {
            return;
        }

        var fieldset = group;
        var preview = editor.querySelector(".logo-header-preview");
        var leftCol = editor.querySelector(".logo-header-left");
        var slot = editor.querySelector(".logo-header-slot");
        var image = editor.querySelector(".logo-placement-image");
        var slotHint = editor.querySelector(".logo-header-slot-hint");
        var details = group.querySelector(".logo-editor-details");
        var controls = editor.querySelector(".logo-placement-controls");
        var scaleInput = editor.querySelector(".logo-scale-input");
        var resetBtn = editor.querySelector(".logo-reset-btn");
        var chooseBtn = group.querySelector(".logo-choose-btn");
        var fileInput = group.querySelector(".logo-file-input");
        var filenameEl = group.querySelector(".logo-upload-filename");
        var errorEl = editor.querySelector(".logo-upload-error");
        var toggleInput = group.querySelector(".logo-enabled-input");
        var statusEl = group.querySelector(".logo-enabled-status");

        var naturalW = 0;
        var naturalH = 0;
        var placement = parsePlacement(editor);
        var drag = null;

        function setError(message) {
            if (!errorEl) {
                return;
            }
            if (message) {
                errorEl.textContent = message;
                errorEl.hidden = false;
            } else {
                errorEl.textContent = "";
                errorEl.hidden = true;
            }
        }

        function getSlotWidth() {
            var target = leftCol || slot;
            if (!target) {
                return 0;
            }
            return target.getBoundingClientRect().width;
        }

        function getReferenceFrameHeight(slotWidth) {
            return slotWidth * (canvasH / canvasW);
        }

        function isLogoShownInPreview() {
            return !!(preview && preview.classList.contains("is-logo-visible"));
        }

        function syncPreviewState() {
            var enabled = !!(toggleInput && toggleInput.checked);
            var hasImage = naturalW > 0 && naturalH > 0;

            if (fieldset) {
                fieldset.classList.toggle("is-enabled", enabled);
            }
            if (statusEl) {
                statusEl.textContent = enabled ? "On" : "Off";
            }
            if (preview) {
                var showLogo = enabled && hasImage;
                preview.classList.toggle("is-logo-visible", showLogo);
                preview.classList.toggle("is-logo-hidden", !showLogo);
            }
            if (controls) {
                controls.classList.toggle("is-preview-muted", hasImage && !enabled);
            }

            if (enabled && hasImage) {
                applyLayout();
            } else if (slot) {
                slot.style.height = "";
            }
        }

        function applyLayout() {
            if (!isLogoShownInPreview() || !image || !slot || !naturalW || !naturalH) {
                return;
            }

            var slotWidth = getSlotWidth();
            if (!slotWidth) {
                return;
            }

            var frameH = getReferenceFrameHeight(slotWidth);
            var layout = computeLayout(naturalW, naturalH, slotWidth, frameH, placement);
            image.style.width = layout.width + "px";
            image.style.height = layout.height + "px";
            image.style.left = layout.left + "px";
            image.style.top = layout.top + "px";

            var slotHeight = Math.max(
                MIN_SLOT_HEIGHT_PX,
                Math.ceil(Math.max(0, layout.top) + layout.height) + SLOT_PADDING_PX
            );
            slot.style.height = slotHeight + "px";

            writePlacement(placement);
            if (scaleInput) {
                scaleInput.value = String(placement.scale);
            }
        }

        function setNaturalSize(w, h, options) {
            options = options || {};
            naturalW = w;
            naturalH = h;
            if (image) {
                image.hidden = false;
            }
            if (slotHint) {
                slotHint.hidden = true;
            }
            if (details) {
                details.open = true;
            }
            fieldset.classList.add("has-logo");
            if (toggleInput) {
                toggleInput.disabled = false;
                if (options.enableToggle && !toggleInput.checked) {
                    toggleInput.checked = true;
                }
            }
            if (scaleInput) {
                scaleInput.disabled = false;
            }
            if (resetBtn) {
                resetBtn.disabled = false;
            }
            syncPreviewState();
        }

        function loadImageFromUrl(url) {
            if (!url || !image) {
                return;
            }
            image.onload = function () {
                setNaturalSize(image.naturalWidth, image.naturalHeight);
            };
            image.onerror = function () {
                setError("Could not load the logo preview.");
            };
            image.src = url;
        }

        function validateFile(file) {
            if (!file) {
                return "No file selected.";
            }
            if (file.size > MAX_UPLOAD_BYTES) {
                return "Logo file must be 8 MB or smaller.";
            }
            if (!file.type.startsWith("image/")) {
                return "Choose an image file (PNG or JPEG).";
            }
            return "";
        }

        function loadFile(file) {
            var err = validateFile(file);
            if (err) {
                setError(err);
                return;
            }
            setError("");
            var reader = new FileReader();
            reader.onload = function () {
                var probe = new Image();
                probe.onload = function () {
                    if (Math.min(probe.naturalWidth, probe.naturalHeight) < MIN_DIMENSION) {
                        setError("Logo image is too small. Use at least 32 pixels on the shortest side.");
                        return;
                    }
                    if (image) {
                        image.src = reader.result;
                        setNaturalSize(probe.naturalWidth, probe.naturalHeight, { enableToggle: true });
                    }
                    if (filenameEl) {
                        filenameEl.textContent = file.name;
                    }
                };
                probe.onerror = function () {
                    setError("Could not read that image. Try PNG or JPEG.");
                };
                probe.src = reader.result;
            };
            reader.readAsDataURL(file);
        }

        if (scaleInput) {
            scaleInput.min = String(scaleMin);
            scaleInput.max = String(scaleMax);
            scaleInput.addEventListener("input", function () {
                placement.scale = clamp(parseFloat(scaleInput.value) || 1, scaleMin, scaleMax);
                applyLayout();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                placement = { scale: 1, offset_x: 0, offset_y: 0 };
                applyLayout();
            });
        }

        if (chooseBtn && fileInput) {
            chooseBtn.addEventListener("click", function () {
                fileInput.click();
            });
            fileInput.addEventListener("change", function () {
                if (fileInput.files && fileInput.files[0]) {
                    loadFile(fileInput.files[0]);
                }
            });
        }

        if (toggleInput) {
            toggleInput.addEventListener("change", syncPreviewState);
            syncPreviewState();
        }

        if (image && slot) {
            image.addEventListener("pointerdown", function (event) {
                if (!naturalW || !naturalH || !isLogoShownInPreview()) {
                    return;
                }
                event.preventDefault();
                image.setPointerCapture(event.pointerId);
                drag = {
                    startX: event.clientX,
                    startY: event.clientY,
                    startOx: placement.offset_x,
                    startOy: placement.offset_y,
                };
            });
            image.addEventListener("pointermove", function (event) {
                if (!drag) {
                    return;
                }
                var slotWidth = getSlotWidth();
                if (!slotWidth) {
                    return;
                }
                var frameH = getReferenceFrameHeight(slotWidth);
                placement.offset_x = clamp(
                    drag.startOx + (event.clientX - drag.startX) / slotWidth,
                    config.offsetMin != null ? config.offsetMin : -1,
                    config.offsetMax != null ? config.offsetMax : 1
                );
                placement.offset_y = clamp(
                    drag.startOy + (event.clientY - drag.startY) / frameH,
                    config.offsetMin != null ? config.offsetMin : -1,
                    config.offsetMax != null ? config.offsetMax : 1
                );
                applyLayout();
            });
            image.addEventListener("pointerup", function (event) {
                if (drag) {
                    drag = null;
                    try {
                        image.releasePointerCapture(event.pointerId);
                    } catch (err) {
                        /* ignore */
                    }
                }
            });
            image.addEventListener("pointercancel", function () {
                drag = null;
            });
        }

        window.addEventListener("resize", function () {
            applyLayout();
        });

        if (details) {
            details.addEventListener("toggle", function () {
                if (details.open) {
                    applyLayout();
                }
            });
        }

        placement = parsePlacement(editor);
        if (editor.getAttribute("data-has-image") === "true") {
            var sourceUrl = editor.getAttribute("data-source-url") || editor.getAttribute("data-preview-url");
            if (sourceUrl) {
                loadImageFromUrl(sourceUrl);
            } else {
                syncPreviewState();
            }
        } else {
            syncPreviewState();
        }
    }

    window.initLogoFieldsUi = function (root) {
        var scope = root || document;
        scope.querySelectorAll(".logo-fields-group").forEach(bindEditor);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            window.initLogoFieldsUi();
        });
    } else {
        window.initLogoFieldsUi();
    }
})();
