/** Classic PDF / logo header geometry — keep in sync with account_api/worker/src/pdf/geometry.js */
export const HEADER_SLOT_FRACTION = 0.6;
export const HEADER_CANVAS_WIDTH = 900;
export const HEADER_CANVAS_HEIGHT = 500;
export const SCALE_MIN = 0.5;
export const SCALE_MAX = 3;

export interface LogoPlacement {
  scale: number;
  offset_x: number;
  offset_y: number;
}

export function defaultPlacement(): LogoPlacement {
  return { scale: 1, offset_x: 0, offset_y: 0 };
}

export function clampPlacement(p: Partial<LogoPlacement>): LogoPlacement {
  return {
    scale: Math.max(SCALE_MIN, Math.min(SCALE_MAX, Number(p.scale) || 1)),
    offset_x: Math.max(-1, Math.min(1, Number(p.offset_x) || 0)),
    offset_y: Math.max(-1, Math.min(1, Number(p.offset_y) || 0)),
  };
}

/** Contain-fit layout matching desktop bake_logo_to_header_slot. */
export function computeLogoLayout(
  naturalW: number,
  naturalH: number,
  frameW: number,
  frameH: number,
  placement: LogoPlacement
) {
  const base = Math.min(frameW / naturalW, frameH / naturalH);
  const scale = base * placement.scale;
  const width = naturalW * scale;
  const height = naturalH * scale;
  const left = (frameW - width) / 2 + placement.offset_x * frameW;
  const top = placement.offset_y * frameH;
  return { width, height, left, top };
}
