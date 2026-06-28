# App assets

Drop your draft files here. They are bundled into the desktop build automatically.

## Splash logo (startup only)

**Path:** `client_app/assets/splash-logo.png`

| Spec | Value |
|------|--------|
| Format | PNG |
| Size | **512 × 512 px** (square) |
| Background | Transparent outside the mark |
| Layout | Keep the frog centred. Outer corners may be cropped on rounded taskbar icons. |
| Colour | FrogsWork greens (`#16a34a`, `#166534`, `#14532d`) per [brand.md](../../docs/commercial/brand.md) |

Shown on **app startup splash** only. Not shown on the Home screen.

If this file is missing, startup shows a plain green placeholder tile.

## Windows icon

**Path:** `client_app/assets/app.ico`

| Spec | Value |
|------|--------|
| Format | ICO (multi-size in one file) |
| Sizes required | **16, 32, 48, 256** px (add 64 and 128 if your tool allows) |
| Source | Export from the same artwork as the splash PNG |
| Readability | Must read clearly at **16 × 16** on the taskbar |

Used for `FrogsWork.exe`, taskbar, Alt+Tab, and window chrome after rebuild.

If this file is missing, Windows uses a generic PyInstaller icon.

## After adding files

```powershell
.\build_client.ps1
```

Restart the dev app to preview the splash (`python app.py` from `client_app/`).

## Optional support email for logo-design form

Set `FROGSWORK_SUPPORT_EMAIL=you@example.com` before starting the app to enable an **Open email app** button on Settings → Logo design. Otherwise users copy the message and use the support URL.
