# FrogsWork Windows installer (Inno Setup)

Builds **`FrogsWork-x.y.z-setup.exe`** from PyInstaller onedir output.

## Prerequisites

- PyInstaller build: `.\build_client.ps1 -Clean` → `client_app\dist\FrogsWork\`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (`ISCC.exe`)

## Build

From repo root (normally invoked by `package_client_release.ps1`):

```powershell
.\scripts\build_installer.ps1 -Version "1.1.0"
```

Output: `client_app\dist\FrogsWork-1.1.0-setup.exe`

Custom PyInstaller folder:

```powershell
.\scripts\build_installer.ps1 -Version "1.1.0" -AppSource "C:\path\to\FrogsWork"
```

## Script

[`FrogsWork.iss`](FrogsWork.iss) — edit install/uninstall behaviour here.

| Setting | Value |
|---------|--------|
| Default install dir | `{localappdata}\Programs\FrogsWork` |
| Privileges | `lowest` (no admin) |
| Uninstall PDF export | `FrogsWork.exe --export-uninstall-data` (optional task, default on) |
| Remove AppData | `{userappdata}\FrogsWork` on uninstall |

## See also

- [RELEASE.md](../docs/commercial/RELEASE.md) — full release pipeline
- [DEPLOY.md](../docs/commercial/DEPLOY.md) — upload to R2 and Pi env
