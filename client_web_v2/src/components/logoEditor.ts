import {
  HEADER_CANVAS_HEIGHT,
  HEADER_CANVAS_WIDTH,
  HEADER_SLOT_FRACTION,
  SCALE_MAX,
  SCALE_MIN,
  clampPlacement,
  computeLogoLayout,
  defaultPlacement,
  type LogoPlacement,
} from "../domain/invoiceHeader";
import { showToast } from "./ui";

export interface LogoEditorState {
  sourceB64: string;
  bakedB64: string;
  placement: LogoPlacement;
  enabled: boolean;
}

export function logoEditorHtml(state: LogoEditorState): string {
  return `
    <div class="logo-editor" id="logo-editor">
      <label class="checkbox"><input type="checkbox" id="logo-enabled" ${state.enabled ? "checked" : ""}> Show logo on invoices</label>
      <div class="field">
        <label>Upload logo</label>
        <input type="file" id="logo-file" accept="image/png,image/jpeg">
      </div>
      <div class="logo-header-preview" id="logo-header-preview">
        <div class="logo-header-left" style="flex: ${HEADER_SLOT_FRACTION}">
          <div class="logo-header-slot" id="logo-header-slot">
            ${
              state.sourceB64
                ? `<img id="logo-drag-img" src="${state.sourceB64}" alt="" draggable="false">`
                : `<p class="hint">No logo</p>`
            }
          </div>
        </div>
        <div class="logo-header-meta" style="flex: ${1 - HEADER_SLOT_FRACTION}">
          <div class="classic-title">Tax Invoice</div>
          <div class="hint">Invoice # · Date · Due</div>
        </div>
      </div>
      <div class="field" ${state.sourceB64 ? "" : "hidden"} id="logo-scale-field">
        <label>Scale <span id="logo-scale-val">${state.placement.scale.toFixed(2)}</span></label>
        <input type="range" id="logo-scale" min="${SCALE_MIN}" max="${SCALE_MAX}" step="0.05" value="${state.placement.scale}">
      </div>
      ${state.sourceB64 ? `<button type="button" class="btn small ghost" id="clear-logo">Remove logo</button>` : ""}
      <p class="hint">Drag the logo to position it in the invoice header slot.</p>
    </div>`;
}

/** Strip logo source from records sent to the API (source stays local for re-editing). */
export function businessRecordForSync(record: Record<string, unknown>): Record<string, unknown> {
  const { logo_source_b64: _source, ...synced } = record;
  return synced;
}

export async function fileToSourceDataUrl(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const maxEdge = 1200;
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not process logo.");
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", 0.88);
}

export function bakeLogoToHeaderSlot(sourceDataUrl: string, placement: LogoPlacement): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = HEADER_CANVAS_WIDTH;
      canvas.height = HEADER_CANVAS_HEIGHT;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("Could not bake logo."));
      // White fill so JPEG has no transparent black edges in PDF.
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const layout = computeLogoLayout(
        img.naturalWidth,
        img.naturalHeight,
        canvas.width,
        canvas.height,
        clampPlacement(placement)
      );
      ctx.drawImage(img, layout.left, layout.top, layout.width, layout.height);
      resolve(canvas.toDataURL("image/jpeg", 0.88));
    };
    img.onerror = () => reject(new Error("Could not load logo image."));
    img.src = sourceDataUrl;
  });
}

/** Update only the logo editor block without rebuilding the whole business form. */
export function refreshLogoEditorSection(
  root: ParentNode,
  state: LogoEditorState,
  onChange: (next: LogoEditorState, reason: "source" | "placement" | "enabled") => void
) {
  const editor = root.querySelector("#logo-editor");
  if (!editor) return;
  const replacement = document.createElement("div");
  replacement.innerHTML = logoEditorHtml(state).trim();
  const nextEditor = replacement.firstElementChild;
  if (!nextEditor) return;
  editor.replaceWith(nextEditor);
  wireLogoEditor(root, state, onChange);
}

export function wireLogoEditor(
  root: ParentNode,
  state: LogoEditorState,
  onChange: (next: LogoEditorState, reason: "source" | "placement" | "enabled") => void
) {
  const slot = root.querySelector("#logo-header-slot") as HTMLElement | null;
  const img = root.querySelector("#logo-drag-img") as HTMLImageElement | null;
  const scaleInput = root.querySelector("#logo-scale") as HTMLInputElement | null;
  const scaleVal = root.querySelector("#logo-scale-val");
  const enabled = root.querySelector("#logo-enabled") as HTMLInputElement | null;

  const applyLayout = () => {
    if (!slot || !img || !img.naturalWidth) return;
    const rect = slot.getBoundingClientRect();
    const layout = computeLogoLayout(
      img.naturalWidth,
      img.naturalHeight,
      rect.width,
      rect.height,
      state.placement
    );
    img.style.position = "absolute";
    img.style.width = `${layout.width}px`;
    img.style.height = `${layout.height}px`;
    img.style.left = `${layout.left}px`;
    img.style.top = `${layout.top}px`;
  };

  const commitBake = async (reason: "placement" | "source" = "placement") => {
    if (!state.sourceB64) {
      state.bakedB64 = "";
      onChange({ ...state }, reason);
      return;
    }
    state.bakedB64 = await bakeLogoToHeaderSlot(state.sourceB64, state.placement);
    onChange({ ...state }, reason);
  };

  img?.addEventListener("load", applyLayout);
  window.addEventListener("resize", applyLayout);
  requestAnimationFrame(applyLayout);

  scaleInput?.addEventListener("input", () => {
    state.placement = clampPlacement({
      ...state.placement,
      scale: Number(scaleInput.value),
    });
    if (scaleVal) scaleVal.textContent = state.placement.scale.toFixed(2);
    applyLayout();
  });
  scaleInput?.addEventListener("change", () => {
    void commitBake();
  });

  enabled?.addEventListener("change", () => {
    state.enabled = Boolean(enabled.checked);
    onChange({ ...state }, "enabled");
  });

  root.querySelector("#logo-file")?.addEventListener("change", async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error("Logo must be under 8 MB.");
      state.sourceB64 = await fileToSourceDataUrl(file);
      state.placement = defaultPlacement();
      state.enabled = true;
      // Defer bake so the editor updates immediately; Save / drag end will bake.
      state.bakedB64 = "";
      onChange({ ...state }, "source");
      void bakeLogoToHeaderSlot(state.sourceB64, state.placement).then((baked) => {
        if (state.sourceB64) {
          state.bakedB64 = baked;
          onChange({ ...state }, "placement");
        }
      });
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : "Logo failed.", "error");
    }
  });

  root.querySelector("#clear-logo")?.addEventListener("click", () => {
    state.sourceB64 = "";
    state.bakedB64 = "";
    state.placement = defaultPlacement();
    state.enabled = false;
    onChange({ ...state }, "source");
  });

  if (img && slot) {
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let startOx = 0;
    let startOy = 0;
    img.addEventListener("pointerdown", (ev) => {
      dragging = true;
      img.setPointerCapture(ev.pointerId);
      startX = ev.clientX;
      startY = ev.clientY;
      startOx = state.placement.offset_x;
      startOy = state.placement.offset_y;
      ev.preventDefault();
    });
    img.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const rect = slot.getBoundingClientRect();
      const dx = (ev.clientX - startX) / rect.width;
      const dy = (ev.clientY - startY) / rect.height;
      state.placement = clampPlacement({
        scale: state.placement.scale,
        offset_x: startOx + dx,
        offset_y: startOy + dy,
      });
      applyLayout();
    });
    img.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false;
      void commitBake();
    });
  }
}

export function readLogoStateFromRecord(record: Record<string, unknown>): LogoEditorState {
  const placement = clampPlacement(
    (record.logo_placement as LogoPlacement) || defaultPlacement()
  );
  return {
    sourceB64: String(record.logo_source_b64 || record.logo_b64 || ""),
    bakedB64: String(record.logo_b64 || ""),
    placement,
    enabled: record.logo_enabled !== false && Boolean(record.logo_b64 || record.logo_source_b64),
  };
}
