"""Logo upload validation and header-slot baking for invoice PDFs."""

from __future__ import annotations

import io
from typing import Any

HEADER_CANVAS_WIDTH = 900
HEADER_CANVAS_HEIGHT = 500
PDF_HEADER_WIDTH_MM = 45
PDF_HEADER_HEIGHT_MM = 25
PDF_HEADER_MAX_HEIGHT_MM = 40

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MIN_DIMENSION_PX = 32
MAX_SOURCE_DIMENSION_PX = 2400
SCALE_MIN = 0.5
SCALE_MAX = 3.0
OFFSET_MIN = -1.0
OFFSET_MAX = 1.0

DEFAULT_PLACEMENT = {"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0}


def default_placement() -> dict[str, float]:
    return dict(DEFAULT_PLACEMENT)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_placement(raw: dict[str, Any] | None = None, *, form: Any = None) -> dict[str, float]:
    """Parse placement from a profile dict or Flask form."""
    if form is not None:
        raw = {
            "scale": form.get("logo_placement_scale", ""),
            "offset_x": form.get("logo_placement_offset_x", ""),
            "offset_y": form.get("logo_placement_offset_y", ""),
        }
    raw = raw or {}

    def _float(key: str, default: float) -> float:
        try:
            return float(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "scale": _clamp(_float("scale", DEFAULT_PLACEMENT["scale"]), SCALE_MIN, SCALE_MAX),
        "offset_x": _clamp(_float("offset_x", DEFAULT_PLACEMENT["offset_x"]), OFFSET_MIN, OFFSET_MAX),
        "offset_y": _clamp(_float("offset_y", DEFAULT_PLACEMENT["offset_y"]), OFFSET_MIN, OFFSET_MAX),
    }


def contain_fit_size(src_w: int, src_h: int, box_w: int, box_h: int) -> tuple[float, float]:
    if src_w <= 0 or src_h <= 0:
        return 0.0, 0.0
    base = min(box_w / src_w, box_h / src_h)
    return src_w * base, src_h * base


def open_logo_upload(file_storage) -> "Image.Image":
    """Open and validate an uploaded logo. Raises ValueError on failure."""
    from PIL import Image

    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("No logo file was uploaded.")

    stream = file_storage.stream
    stream.seek(0)
    data = stream.read()
    if not data:
        raise ValueError("Logo file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Logo file must be 8 MB or smaller.")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError("Could not read that image. Try PNG or JPEG.") from exc

    if getattr(img, "is_animated", False):
        img.seek(0)

    return prepare_source_image(img)


def prepare_source_image(img: "Image.Image") -> "Image.Image":
    from PIL import Image

    src = img.convert("RGBA")
    w, h = src.size
    if min(w, h) < MIN_DIMENSION_PX:
        raise ValueError("Logo image is too small. Use at least 32 pixels on the shortest side.")
    longest = max(w, h)
    if longest > MAX_SOURCE_DIMENSION_PX:
        src.thumbnail((MAX_SOURCE_DIMENSION_PX, MAX_SOURCE_DIMENSION_PX), Image.Resampling.LANCZOS)
    return src


def content_alpha_bbox(img: "Image.Image") -> tuple[int, int, int, int] | None:
    """Return bounding box of non-transparent pixels, or None if empty."""
    alpha = img.convert("RGBA").getchannel("A")
    return alpha.getbbox()


def crop_to_content_bounds(img: "Image.Image") -> "Image.Image":
    """Crop to tight bounds around visible logo pixels."""
    bbox = content_alpha_bbox(img)
    if not bbox:
        return img
    return img.crop(bbox)


def pdf_draw_dimensions_mm(pixel_width: int, pixel_height: int) -> tuple[float, float]:
    """Map cropped baked pixel dimensions to PDF draw size in mm."""
    if pixel_width <= 0 or pixel_height <= 0:
        return float(PDF_HEADER_WIDTH_MM), float(PDF_HEADER_HEIGHT_MM)

    draw_w = float(PDF_HEADER_WIDTH_MM)
    draw_h = draw_w * (pixel_height / pixel_width)
    max_h = float(PDF_HEADER_MAX_HEIGHT_MM)
    if draw_h > max_h:
        draw_h = max_h
        draw_w = draw_h * (pixel_width / pixel_height)
    return draw_w, draw_h


def bake_logo_to_header_slot(source: "Image.Image", placement: dict[str, float] | None = None) -> "Image.Image":
    """Composite source logo into the fixed header canvas using placement."""
    from PIL import Image

    placement = parse_placement(placement)
    src = source.convert("RGBA")
    iw, ih = src.size
    canvas_w, canvas_h = HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT

    base = min(canvas_w / iw, canvas_h / ih)
    display_scale = base * placement["scale"]
    new_w = max(1, int(round(iw * display_scale)))
    new_h = max(1, int(round(ih * display_scale)))
    resized = src.resize((new_w, new_h), Image.Resampling.LANCZOS)

    x = int(round((canvas_w - new_w) / 2 + placement["offset_x"] * canvas_w))
    y = int(round((canvas_h - new_h) / 2 + placement["offset_y"] * canvas_h))

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.paste(resized, (x, y), resized)
    return crop_to_content_bounds(canvas)


def editor_config() -> dict[str, int | float]:
    """Constants exposed to the placement editor UI."""
    return {
        "canvasWidth": HEADER_CANVAS_WIDTH,
        "canvasHeight": HEADER_CANVAS_HEIGHT,
        "scaleMin": SCALE_MIN,
        "scaleMax": SCALE_MAX,
        "offsetMin": OFFSET_MIN,
        "offsetMax": OFFSET_MAX,
    }
