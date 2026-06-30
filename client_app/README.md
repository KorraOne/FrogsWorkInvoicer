# FrogsWork (client_app)

Commercial desktop sales invoicing app.

- **Product name:** FrogsWork
- **Repo folder:** `client_app/`
- **Build output:** `FrogsWork.exe`
- **Entry:** `app.py` (+ `desktop_shell.py` for windowed mode)
- **AppData:** `%APPDATA%\FrogsWork\`

See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout and request flow.

## Docs

[`../docs/README.md`](../docs/README.md) · [naming conventions](../docs/naming.md)

OS integration (paths, dialogs, updates): [`app_platform/`](app_platform/).

## Dev

```powershell
# From repo root
.\scripts\start-dev.ps1 -DevBrowser
```

Seed test data:

```powershell
.\scripts\reset-dev.ps1 -SeedOnly -Force
# or replace existing seed customers/invoices:
.\scripts\reset-dev.ps1 -SeedOnly -ResetSeed -Force
```

## Build

```powershell
.\client_app\build.ps1
# Full release (installer + update zip):
.\scripts\package_client_release.ps1 -Version "1.1.0" -ReleaseNotes "..."
```

Install: **Inno Setup** `FrogsWork-x.y.z-setup.exe` → `%LOCALAPPDATA%\Programs\FrogsWork\`. See [installer/README.md](installer/README.md) and [DEPLOY.md](../docs/DEPLOY.md).
