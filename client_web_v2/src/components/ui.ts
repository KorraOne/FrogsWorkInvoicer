export function showToast(message: string, kind: "info" | "error" | "success" = "info") {
  let host = document.getElementById("toast-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "toast-host";
    host.className = "toast-host";
    document.body.appendChild(host);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.textContent = message;
  host.appendChild(el);
  window.setTimeout(() => {
    el.classList.add("toast-out");
    window.setTimeout(() => el.remove(), 280);
  }, 2800);
}

const SPRING_BACK = "transform 0.38s cubic-bezier(0.2, 0.9, 0.2, 1.12)";
const DISMISS_OUT = "transform 0.22s cubic-bezier(0.4, 0, 1, 1)";
const COMMIT_PX = 8;
const DISMISS_DY = 100;
const DISMISS_VY = 0.55; // px/ms
const RUBBER_UP = 0.28;
const RUBBER_MAX = 42;

type Sample = { y: number; t: number };

/** Pointer-drag the sheet grab zone to dismiss (rubber-band + spring). */
export function wireSheetGrabDismiss(
  overlay: HTMLElement,
  sheet: HTMLElement,
  onDismiss: () => void
) {
  document.body.classList.add("sheet-open");
  const unlock = () => document.body.classList.remove("sheet-open");
  const observer = new MutationObserver(() => {
    if (!document.body.contains(overlay)) {
      unlock();
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true });

  const handle = sheet.querySelector(".sheet-handle") as HTMLElement | null;
  const title = sheet.querySelector(".sheet-title") as HTMLElement | null;
  const grabTargets = [handle, title].filter(Boolean) as HTMLElement[];
  if (!grabTargets.length) return;

  let startY = 0;
  let currentY = 0;
  let dragging = false;
  let committed = false;
  let pointerId: number | null = null;
  let samples: Sample[] = [];
  let captureEl: HTMLElement | null = null;

  const applyY = (raw: number) => {
    let y = raw;
    if (y < 0) y = Math.max(-RUBBER_MAX, y * RUBBER_UP);
    currentY = y;
    sheet.style.transition = "none";
    sheet.style.willChange = "transform";
    sheet.style.transform = y ? `translateY(${y}px)` : "";
  };

  const velocity = (): number => {
    if (samples.length < 2) return 0;
    const a = samples[0];
    const b = samples[samples.length - 1];
    const dt = Math.max(1, b.t - a.t);
    return (b.y - a.y) / dt;
  };

  const pushSample = (y: number, t: number) => {
    samples.push({ y, t });
    if (samples.length > 5) samples.shift();
  };

  const finishDismiss = () => {
    sheet.style.transition = DISMISS_OUT;
    sheet.style.transform = `translateY(${Math.max(currentY, sheet.offsetHeight + 24)}px)`;
    window.setTimeout(() => {
      unlock();
      onDismiss();
    }, 200);
  };

  const springHome = () => {
    sheet.style.transition = SPRING_BACK;
    sheet.style.transform = "translateY(0px)";
    window.setTimeout(() => {
      sheet.style.transform = "";
      sheet.style.willChange = "";
      sheet.style.transition = "";
    }, 400);
  };

  const onMove = (e: PointerEvent) => {
    if (!dragging || e.pointerId !== pointerId) return;
    const dy = e.clientY - startY;
    if (!committed && Math.abs(dy) < COMMIT_PX) return;
    if (!committed) {
      committed = true;
    }
    e.preventDefault();
    pushSample(e.clientY, e.timeStamp);
    applyY(dy);
  };

  const onUp = (e: PointerEvent) => {
    if (!dragging || e.pointerId !== pointerId) return;
    dragging = false;
    pushSample(e.clientY, e.timeStamp);
    const vy = velocity();
    try {
      captureEl?.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    pointerId = null;
    captureEl = null;

    if (!committed) {
      sheet.style.willChange = "";
      return;
    }

    const dismiss = currentY > DISMISS_DY || (currentY > 40 && vy > DISMISS_VY);
    if (dismiss) finishDismiss();
    else springHome();
  };

  const onDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    dragging = true;
    committed = false;
    pointerId = e.pointerId;
    startY = e.clientY;
    currentY = 0;
    samples = [{ y: e.clientY, t: e.timeStamp }];
    captureEl = e.currentTarget as HTMLElement;
    try {
      captureEl.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    e.preventDefault();
  };

  for (const el of grabTargets) {
    el.addEventListener("pointerdown", onDown);
  }

  // Block scroll through the dimmed backdrop.
  overlay.addEventListener(
    "touchmove",
    (e) => {
      if (e.target === overlay) e.preventDefault();
    },
    { passive: false }
  );
}

export function openSheet(opts: {
  title: string;
  bodyHtml: string;
  actions?: Array<{ id: string; label: string; className?: string; close?: boolean }>;
}): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "sheet-overlay";
    overlay.innerHTML = `
      <div class="sheet" role="dialog" aria-modal="true" aria-label="${opts.title.replace(/"/g, "")}">
        <div class="sheet-handle" aria-hidden="true"></div>
        <h3 class="sheet-title">${opts.title}</h3>
        <div class="sheet-body">${opts.bodyHtml}</div>
        <div class="sheet-actions">
          ${(opts.actions || [{ id: "close", label: "Close", className: "btn ghost", close: true }])
            .map(
              (a) =>
                `<button type="button" class="btn ${a.className || "btn secondary"}" data-sheet-action="${a.id}">${a.label}</button>`
            )
            .join("")}
        </div>
      </div>`;
    const sheet = overlay.querySelector(".sheet") as HTMLElement;
    const close = (value: string | null) => {
      document.body.classList.remove("sheet-open");
      overlay.remove();
      resolve(value);
    };
    wireSheetGrabDismiss(overlay, sheet, () => close(null));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });
    overlay.querySelectorAll("[data-sheet-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = (btn as HTMLElement).dataset.sheetAction || "close";
        const action = (opts.actions || []).find((a) => a.id === id);
        if (!action || action.close !== false) close(id);
        else close(id);
      });
    });
    document.body.appendChild(overlay);
  });
}

export async function confirmSheet(message: string, confirmLabel = "Confirm"): Promise<boolean> {
  const result = await openSheet({
    title: "Confirm",
    bodyHtml: `<p class="hint">${message}</p>`,
    actions: [
      { id: "cancel", label: "Cancel", className: "btn secondary" },
      { id: "confirm", label: confirmLabel, className: "btn danger" },
    ],
  });
  return result === "confirm";
}

export function emptyStateHtml(title: string, hint: string, ctaId?: string, ctaLabel?: string): string {
  return `<div class="empty-state">
    <p class="empty-title">${title}</p>
    <p class="hint">${hint}</p>
    ${ctaId && ctaLabel ? `<button type="button" class="btn primary" id="${ctaId}">${ctaLabel}</button>` : ""}
  </div>`;
}
