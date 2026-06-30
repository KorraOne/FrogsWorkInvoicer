# FrogsWork brand guide

Product identity and visual system for the commercial desktop app. Implementation lives in [`client_app/static/theme.css`](../client_app/static/theme.css).

## Product

| | |
|---|---|
| **Name** | FrogsWork |
| **Developer** | KorraOne |
| **Tagline** | Sales invoicing for Australian sole traders |
| **Role** | Outgoing sales invoices / accounts receivable only |

**Personality:** Calm, capable, local-first. Professional enough for customer-facing PDFs; simple enough for daily non-technical use.

**Voice:** Plain English, action-oriented labels, short hints under buttons. Developer credit stays in the footer only.

## Color palette

| Token | Hex | Use |
|-------|-----|-----|
| `--fw-bg-page` | `#f0fdf4` | App page base |
| `--fw-bg-top` | `#ecfdf5` | Gradient start |
| `--fw-bg-mid` | `#d1fae5` | Gradient mid |
| `--fw-bg-bottom` | `#a7f3d0` | Splash gradient end (strong); avoid on dense forms |
| `--fw-green-900` | `#14532d` | Brand headings (Home) |
| `--fw-green-800` | `#166534` | Taglines |
| `--fw-green-700` | `#15803d` | Links, footer |
| `--fw-green-600` | `#16a34a` | Primary buttons |
| `--fw-green-500` | `#22c55e` | Progress, highlights |
| `--fw-green-300` | `#86efac` | Focus rings |
| `--fw-surface` | `#ffffff` | Cards, forms |
| `--fw-text` | `#1f2937` | Body copy |
| `--fw-error` | `#c0392b` | Errors (unchanged) |

## Typography

- **UI:** Segoe UI, system-ui, sans-serif
- **Sizes:** Keep existing large-type accessibility (1.25rem body, 56px+ button targets)

## Layout rules

- **Page:** Soft green radial wash via `body.app-shell`
- **Content:** White cards on the wash: never full-strength splash gradient behind long forms
- **Primary action:** One green CTA per screen
- **Secondary:** White + green border

## Do / don't

| Do | Don't |
|----|-------|
| Use CSS variables from `theme.css` | Hardcode hex blues from the legacy invoice app |
| Keep tax invoice PDFs neutral (black/white) | Brand PDFs with green marketing |
| Sync splash colors via shared `theme.css` | Drift splash and app palettes |
| Credit KorraOne in footer links only | Repeat developer name in body copy |

## Configurable URLs

Set in [`client_app/app_config.py`](../client_app/app_config.py):

- `APP_DATA_DIR_NAME`: local data folder under `%APPDATA%` (default: `FrogsWork`)
- `APP_BRAND_URL`: FrogsWork marketing site (default: https://frogswork.com)
- `APP_BRAND_DEVELOPER_URL`: KorraOne portfolio (default: https://korraone.com)
- `APP_SUPPORT_URL`: Support (default: https://korraone.com/support)

## Assets

| File | Purpose |
|------|---------|
| `client_app/assets/splash-logo.png` | Startup splash only (512×512 PNG, transparent) |
| `client_app/assets/app.ico` | Windows exe icon (16, 32, 48, 256 px in one ICO) |

Add your own draft files to that folder. See [`client_app/assets/README.md`](../client_app/assets/README.md) for exact specs.

The Home screen does not show the logo.
