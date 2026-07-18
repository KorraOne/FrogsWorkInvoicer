"""Tests for invoicing.logo and business logo baking."""

import io
import os

import pytest
from PIL import Image

from invoicing.logo import (
    HEADER_CANVAS_HEIGHT,
    HEADER_CANVAS_WIDTH,
    bake_logo_to_header_slot,
    contain_fit_size,
    crop_to_content_bounds,
    default_placement,
    open_logo_upload,
    parse_placement,
    pdf_draw_dimensions_mm,
    prepare_source_image,
)


class _FakeUpload:
    def __init__(self, data: bytes, filename="logo.png"):
        self.stream = io.BytesIO(data)
        self.filename = filename

    def read(self):
        self.stream.seek(0)
        return self.stream.read()


def _png_bytes(size):
    img = Image.new("RGBA", size, (200, 40, 40, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_contain_fit_size_square_in_wide_box():
    w, h = contain_fit_size(100, 100, 900, 500)
    assert h == 500
    assert w == 500


def test_bake_output_dimensions():
    src = Image.new("RGBA", (200, 800), (0, 120, 200, 255))
    baked = bake_logo_to_header_slot(src, default_placement())
    assert baked.size == (HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)


def test_bake_keeps_full_canvas():
    src = Image.new("RGBA", (100, 100), (0, 120, 200, 255))
    baked = bake_logo_to_header_slot(src, {"scale": 0.5, "offset_x": 0.0, "offset_y": 0.0})
    assert baked.size == (HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)


def test_bake_top_aligns_at_default():
    src = Image.new("RGBA", (200, 100), (0, 120, 200, 255))
    baked = bake_logo_to_header_slot(src, default_placement())
    alpha = baked.getchannel("A")
    bbox = alpha.getbbox()
    assert bbox is not None
    assert bbox[1] == 0


def test_bake_portrait_with_scale_not_tiny():
    src = Image.new("RGBA", (200, 800), (0, 120, 200, 255))
    baked_default = bake_logo_to_header_slot(src, default_placement())
    baked_zoomed = bake_logo_to_header_slot(src, {"scale": 2.5, "offset_x": 0.0, "offset_y": 0.0})
    default_alpha = sum(baked_default.getchannel("A").getdata())
    zoomed_alpha = sum(baked_zoomed.getchannel("A").getdata())
    assert zoomed_alpha > default_alpha * 1.5


def test_crop_to_content_bounds_trims_padding():
    canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (40, 60), (255, 0, 0, 255)), (80, 70))
    cropped = crop_to_content_bounds(canvas)
    assert cropped.size == (40, 60)


def test_pdf_draw_dimensions_mm_full_canvas():
    from invoicing.logo import PDF_HEADER_SLOT_WIDTH_MM

    draw_w, draw_h = pdf_draw_dimensions_mm(HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)
    assert draw_w == pytest.approx(PDF_HEADER_SLOT_WIDTH_MM)
    assert draw_h == pytest.approx(PDF_HEADER_SLOT_WIDTH_MM * (HEADER_CANVAS_HEIGHT / HEADER_CANVAS_WIDTH))


def test_pdf_draw_dimensions_mm_preserves_offset_canvas():
    from invoicing.logo import PDF_HEADER_SLOT_WIDTH_MM

    draw_w, draw_h = pdf_draw_dimensions_mm(HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)
    assert draw_w == pytest.approx(PDF_HEADER_SLOT_WIDTH_MM)
    assert draw_h / draw_w == pytest.approx(HEADER_CANVAS_HEIGHT / HEADER_CANVAS_WIDTH)


def test_pdf_draw_dimensions_mm_scales_by_aspect():
    draw_w, draw_h = pdf_draw_dimensions_mm(900, 450)
    assert draw_h / draw_w == pytest.approx(0.5)


def test_parse_placement_clamps_values():
    placement = parse_placement({"scale": 9, "offset_x": 2, "offset_y": -3})
    assert placement["scale"] == 3.0
    assert placement["offset_x"] == 1.0
    assert placement["offset_y"] == -1.0


def test_open_logo_upload_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        open_logo_upload(_FakeUpload(b"", "empty.png"))


def test_open_logo_upload_accepts_png():
    img = open_logo_upload(_FakeUpload(_png_bytes((120, 80)), "test.png"))
    assert img.size == (120, 80)


def test_prepare_source_image_crops_transparent_padding():
    canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (40, 60), (255, 0, 0, 255)), (80, 70))
    out = prepare_source_image(canvas)
    assert out.size == (40, 60)


def test_editor_config_includes_pdf_constants():
    from invoicing.logo import PDF_HEADER_MAX_HEIGHT_MM, PDF_HEADER_SLOT_WIDTH_MM, editor_config

    cfg = editor_config()
    assert cfg["pdfSlotWidthMm"] == PDF_HEADER_SLOT_WIDTH_MM
    assert cfg["pdfMaxHeightMm"] == PDF_HEADER_MAX_HEIGHT_MM


def test_preview_and_pdf_width_match_for_wide_logo():
    from invoicing.logo import PDF_HEADER_SLOT_WIDTH_MM

    path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "sample-logo.png",
    )
    if not os.path.isfile(path):
        pytest.skip("sample logo missing")
    src = Image.open(path)
    baked = bake_logo_to_header_slot(src, default_placement())
    draw_w, draw_h = pdf_draw_dimensions_mm(*baked.size)
    assert baked.size == (HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)
    assert draw_w == pytest.approx(PDF_HEADER_SLOT_WIDTH_MM)


def test_prepare_source_image_downscales_large():
    src = Image.new("RGBA", (4000, 2000), (10, 10, 10, 255))
    out = prepare_source_image(src)
    assert max(out.size) <= 2400


def test_migrate_logo_profile_creates_source(tmp_path, monkeypatch):
    import storage.businesses as businesses

    logos = tmp_path / "logos"
    logos.mkdir()
    monkeypatch.setattr(businesses, "_logos_dir", lambda: str(logos))

    baked = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
    baked.save(logos / "acme.png")

    profile = {"logo_filename": "acme.png", "logo_enabled": True}
    migrated = businesses._migrate_logo_profile("Acme", profile)
    assert migrated["logo_source_filename"] == "acme-source.png"
    assert (logos / "acme-source.png").is_file()


def test_apply_business_logo_bakes_upload(tmp_path, monkeypatch):
    import storage.businesses as businesses

    logos = tmp_path / "logos"
    logos.mkdir()
    monkeypatch.setattr(businesses, "_logos_dir", lambda: str(logos))

    profile = {}
    businesses.apply_business_logo(
        "Acme Co",
        file_storage=_FakeUpload(_png_bytes((300, 100)), "wide.png"),
        placement=default_placement(),
        profile=profile,
    )
    assert profile["logo_filename"] == "acme-co.png"
    assert profile["logo_source_filename"] == "acme-co-source.png"
    baked = Image.open(logos / "acme-co.png")
    assert baked.size == (HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT)


def test_needs_logo_rebake_legacy_cropped_bake(tmp_path, monkeypatch):
    import storage.businesses as businesses

    logos = tmp_path / "logos"
    logos.mkdir()
    monkeypatch.setattr(businesses, "_logos_dir", lambda: str(logos))

    Image.new("RGBA", (120, 80), (255, 0, 0, 255)).save(logos / "acme.png")
    Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(logos / "acme-source.png")

    profile = {
        "logo_filename": "acme.png",
        "logo_source_filename": "acme-source.png",
        "logo_placement": default_placement(),
    }
    assert businesses._needs_logo_rebake(profile) is True


def test_needs_logo_rebake_skips_full_canvas_bake(tmp_path, monkeypatch):
    import storage.businesses as businesses

    logos = tmp_path / "logos"
    logos.mkdir()
    monkeypatch.setattr(businesses, "_logos_dir", lambda: str(logos))

    Image.new("RGBA", (HEADER_CANVAS_WIDTH, HEADER_CANVAS_HEIGHT), (255, 0, 0, 255)).save(
        logos / "acme.png"
    )
    Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(logos / "acme-source.png")

    profile = {
        "logo_filename": "acme.png",
        "logo_source_filename": "acme-source.png",
        "logo_placement": default_placement(),
    }
    assert businesses._needs_logo_rebake(profile) is False
