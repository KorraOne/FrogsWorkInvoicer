"""Business profile persistence (invoice sender / From details)."""

import json
import os
import re

from storage._json_cache import cached_read, invalidate
from storage.bootstrap import get_data_path

DEFAULT_BUSINESS_PROFILE = {
    "address_line1": "",
    "address_line2": "",
    "suburb": "",
    "state": "",
    "postcode": "",
    "abn": "",
    "gst_registered": False,
    "account_name": "",
    "bsb": "",
    "acc": "",
    "invoice_counter": 1,
    "logo_enabled": False,
    "logo_filename": "",
    "logo_source_filename": "",
    "logo_placement": None,
}

_LEGACY_SETTINGS_KEYS = (
    "business_name",
    "business_address",
    "business_abn",
    "gst_registered",
    "account_name",
    "bsb",
    "acc",
    "invoice_counter",
)


def _businesses_path():
    return os.path.join(get_data_path(), "businesses.json")


def _profile_from_legacy_settings(settings):
    name = (settings.get("business_name") or "").strip()
    address = (settings.get("business_address") or "").strip()
    abn = (settings.get("business_abn") or "").strip()
    account_name = (settings.get("account_name") or "").strip()
    bsb = (settings.get("bsb") or "").strip()
    acc = (settings.get("acc") or "").strip()
    gst_registered = bool(settings.get("gst_registered"))
    invoice_counter = int(settings.get("invoice_counter", 1) or 1)

    if not any([name, address, abn, account_name, bsb, acc, gst_registered]):
        return None, None

    profile_name = name or "My business"
    from invoicing.address import migrate_legacy_address

    addr = migrate_legacy_address(address)
    profile = {
        **addr,
        "abn": abn,
        "gst_registered": gst_registered,
        "account_name": account_name,
        "bsb": bsb,
        "acc": acc,
        "invoice_counter": invoice_counter,
    }
    return profile_name, profile


def _migrate_structured_addresses_if_needed(businesses):
    from invoicing.address import migrate_legacy_address

    changed = False
    for name, profile in (businesses or {}).items():
        if not isinstance(profile, dict):
            continue
        if any(k in profile for k in ("address_line1", "suburb", "state", "postcode")):
            continue
        legacy = (profile.get("address") or "").strip()
        if not legacy:
            profile.setdefault("address_line1", "")
            profile.setdefault("address_line2", "")
            profile.setdefault("suburb", "")
            profile.setdefault("state", "")
            profile.setdefault("postcode", "")
            changed = True
            continue
        profile.update(migrate_legacy_address(legacy))
        changed = True
    return changed


def _migrate_from_settings_if_needed():
    from storage.settings import load_settings, save_settings

    path = _businesses_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
        if existing:
            return existing

    settings = load_settings()
    profile_name, profile = _profile_from_legacy_settings(settings)
    if not profile:
        return {}

    businesses = {profile_name: profile}
    save_businesses(businesses)

    settings["default_business"] = profile_name
    for key in _LEGACY_SETTINGS_KEYS:
        settings.pop(key, None)
    save_settings(settings)
    return businesses


def load_businesses():
    path = _businesses_path()

    def _read():
        if not os.path.exists(path):
            migrated = _migrate_from_settings_if_needed()
            if migrated:
                return migrated
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            migrated = _migrate_from_settings_if_needed()
            return migrated if migrated else {}
        if _migrate_structured_addresses_if_needed(data):
            save_businesses(data)
        return data

    if not os.path.exists(path):
        return _read()
    return cached_read(path, _read)


def save_businesses(businesses):
    path = _businesses_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(businesses, f, indent=2)
    invalidate(path)


def business_name_exists(name, exclude=None):
    businesses = load_businesses()
    for existing in businesses:
        if existing.lower() == name.lower() and existing != exclude:
            return True
    return False


def rename_business(old_name, new_name, profile):
    """Move a business profile to a new display name key."""
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not old_name or not new_name:
        raise ValueError("Enter a business name.")
    if old_name == new_name:
        businesses = load_businesses()
        businesses[old_name] = profile
        save_businesses(businesses)
        return new_name
    if business_name_exists(new_name, exclude=old_name):
        raise ValueError("A business with this name already exists.")

    businesses = load_businesses()
    if old_name not in businesses:
        raise ValueError("Business not found.")

    del businesses[old_name]
    businesses[new_name] = profile
    save_businesses(businesses)

    if get_default_business_name() == old_name:
        set_default_business(new_name)
    return new_name


def get_default_business_name():
    from storage.settings import load_settings

    settings = load_settings()
    default_name = (settings.get("default_business") or "").strip()
    businesses = load_businesses()
    if default_name in businesses:
        return default_name
    if businesses:
        return next(iter(businesses))
    return ""


def set_default_business(name):
    from storage.settings import load_settings, save_settings

    settings = load_settings()
    settings["default_business"] = name
    save_settings(settings)


def resolve_business(name=None):
    """Return (name, profile dict) for the given or default business."""
    businesses = load_businesses()
    if not businesses:
        return "", {}

    if name:
        name = name.strip()
        if name in businesses:
            return name, _migrate_logo_profile(name, dict(businesses[name]))

    default_name = get_default_business_name()
    if default_name in businesses:
        return default_name, _migrate_logo_profile(default_name, dict(businesses[default_name]))

    first_name = next(iter(businesses))
    return first_name, _migrate_logo_profile(first_name, dict(businesses[first_name]))


def invoice_business_name(inv):
    """Business name for an invoice record (handles legacy invoices)."""
    stored = (inv.get("business_name") or "").strip()
    if stored:
        return stored
    return get_default_business_name()


def business_invoice_fields(name, profile=None):
    """Map a business profile to invoice_data sender fields."""
    from invoicing.address import format_address_multiline

    if profile is None:
        name, profile = resolve_business(name)
    profile = profile or {}
    logo_path = None
    if profile.get("logo_enabled") and profile.get("logo_filename"):
        candidate = os.path.join(_logos_dir(), profile.get("logo_filename"))
        if os.path.isfile(candidate):
            logo_path = candidate
    return {
        "business_name": name,
        "business_address": format_address_multiline(profile) or profile.get("address", ""),
        "business_abn": profile.get("abn", ""),
        "account_name": profile.get("account_name", ""),
        "bsb": profile.get("bsb", ""),
        "acc": profile.get("acc", ""),
        "gst_registered": bool(profile.get("gst_registered")),
        "logo_enabled": bool(profile.get("logo_enabled")),
        "logo_path": logo_path,
    }


def normalize_business_profile(form_data, existing=None):
    """Build a profile dict from form fields."""
    existing = existing or {}
    return {
        "address_line1": form_data.get("address_line1", existing.get("address_line1", "")).strip(),
        "address_line2": form_data.get("address_line2", existing.get("address_line2", "")).strip(),
        "suburb": form_data.get("suburb", existing.get("suburb", "")).strip(),
        "state": form_data.get("state", existing.get("state", "")).strip(),
        "postcode": form_data.get("postcode", existing.get("postcode", "")).strip(),
        "abn": form_data.get("abn", existing.get("abn", "")).strip(),
        "gst_registered": form_data.get("gst_registered", existing.get("gst_registered", False)),
        "account_name": form_data.get("account_name", existing.get("account_name", "")).strip(),
        "bsb": form_data.get("bsb", existing.get("bsb", "")).strip(),
        "acc": form_data.get("acc", existing.get("acc", "")).strip(),
        "invoice_counter": int(existing.get("invoice_counter", 1) or 1),
        "logo_enabled": bool(form_data.get("logo_enabled", existing.get("logo_enabled", False))),
        "logo_filename": form_data.get("logo_filename", existing.get("logo_filename", "")).strip(),
        "logo_source_filename": form_data.get(
            "logo_source_filename", existing.get("logo_source_filename", "")
        ).strip(),
        "logo_placement": form_data.get("logo_placement", existing.get("logo_placement")) or None,
    }


def _logos_dir():
    path = os.path.join(get_data_path(), "logos")
    os.makedirs(path, exist_ok=True)
    return path


def business_logo_filename(business_name):
    base = re.sub(r"[^a-zA-Z0-9]+", "-", str(business_name or "").strip()).strip("-").lower()
    if not base:
        base = "business"
    return f"{base}.png"


def business_logo_source_filename(business_name):
    base = re.sub(r"[^a-zA-Z0-9]+", "-", str(business_name or "").strip()).strip("-").lower()
    if not base:
        base = "business"
    return f"{base}-source.png"


def _logo_path(filename):
    if not filename:
        return ""
    return os.path.join(_logos_dir(), filename)


def _migrate_logo_profile(business_name, profile):
    """Backfill placement/source fields for profiles saved before the editor."""
    import shutil

    from invoicing.logo import default_placement

    if not isinstance(profile, dict):
        return profile
    profile.setdefault("logo_source_filename", "")
    if not isinstance(profile.get("logo_placement"), dict):
        profile["logo_placement"] = default_placement()
    baked = (profile.get("logo_filename") or "").strip()
    source = (profile.get("logo_source_filename") or "").strip()
    if baked and not source:
        source_name = business_logo_source_filename(business_name)
        baked_path = _logo_path(baked)
        source_path = _logo_path(source_name)
        if os.path.isfile(baked_path) and not os.path.isfile(source_path):
            shutil.copy2(baked_path, source_path)
        if os.path.isfile(source_path):
            profile["logo_source_filename"] = source_name
    if _needs_logo_rebake(profile):
        try:
            rebake_business_logo(business_name, profile.get("logo_placement"), profile)
        except (OSError, ValueError):
            pass
    return profile


def _needs_logo_rebake(profile):
    """True when baked logo is missing or still uses the legacy full canvas size."""
    baked = (profile.get("logo_filename") or "").strip()
    source = (profile.get("logo_source_filename") or "").strip()
    if not baked or not source:
        return False
    if not os.path.isfile(_logo_path(source)):
        return False
    baked_path = _logo_path(baked)
    if not os.path.isfile(baked_path):
        return True
    try:
        from PIL import Image

        from invoicing.logo import HEADER_CANVAS_HEIGHT, HEADER_CANVAS_WIDTH

        with Image.open(baked_path) as img:
            w, h = img.size
        return w == HEADER_CANVAS_WIDTH and h == HEADER_CANVAS_HEIGHT
    except OSError:
        return True


def apply_business_logo(business_name, *, file_storage=None, placement, profile):
    """
    Save source (if uploaded), bake header slot PNG, update profile logo fields.

    Returns updated filenames dict.
    """
    from invoicing.logo import bake_logo_to_header_slot, default_placement, open_logo_upload, parse_placement

    placement = parse_placement(placement or profile.get("logo_placement") or default_placement())
    baked_name = business_logo_filename(business_name)
    source_name = business_logo_source_filename(business_name)
    baked_path = _logo_path(baked_name)
    source_path = _logo_path(source_name)

    if file_storage and file_storage.filename:
        source_img = open_logo_upload(file_storage)
        source_img.save(source_path, format="PNG", optimize=True)
        profile["logo_source_filename"] = source_name
    elif profile.get("logo_source_filename"):
        source_path = _logo_path(profile["logo_source_filename"])
        source_name = profile["logo_source_filename"]
        if not os.path.isfile(source_path):
            legacy = _logo_path(profile.get("logo_filename", ""))
            if os.path.isfile(legacy):
                import shutil

                shutil.copy2(legacy, source_path)
                profile["logo_source_filename"] = source_name
            else:
                raise ValueError("Logo source file is missing. Upload the logo again.")
        from PIL import Image

        source_img = Image.open(source_path)
        source_img.load()
    elif profile.get("logo_filename") and os.path.isfile(_logo_path(profile["logo_filename"])):
        import shutil

        source_path = _logo_path(source_name)
        shutil.copy2(_logo_path(profile["logo_filename"]), source_path)
        profile["logo_source_filename"] = source_name
        from PIL import Image

        source_img = Image.open(source_path)
        source_img.load()
    else:
        raise ValueError("Upload a logo image first.")

    baked = bake_logo_to_header_slot(source_img, placement)
    baked.save(baked_path, format="PNG", optimize=True)
    profile["logo_filename"] = baked_name
    profile["logo_placement"] = placement
    return {"logo_filename": baked_name, "logo_source_filename": profile.get("logo_source_filename", source_name)}


def rebake_business_logo(business_name, placement, profile):
    """Re-bake using existing source and new placement."""
    return apply_business_logo(business_name, placement=placement, profile=profile)


def save_business_logo(business_name, file_storage, placement=None):
    """Legacy entry point: save upload with default placement."""
    from invoicing.logo import default_placement

    profile = {"logo_placement": placement or default_placement()}
    apply_business_logo(business_name, file_storage=file_storage, placement=placement, profile=profile)
    return profile["logo_filename"]


def remove_business_logo(business_name, profile=None):
    filenames = []
    if isinstance(profile, dict):
        for key in ("logo_filename", "logo_source_filename"):
            name = (profile.get(key) or "").strip()
            if name:
                filenames.append(name)
    elif profile:
        filenames.append(profile)
    else:
        filenames = [business_logo_filename(business_name), business_logo_source_filename(business_name)]

    seen = set()
    for name in filenames:
        if not name or name in seen:
            continue
        seen.add(name)
        path = _logo_path(name)
        if os.path.isfile(path):
            os.remove(path)
