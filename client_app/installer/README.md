# FrogsWork Windows installer (Inno Setup)

Builds **`FrogsWork-x.y.z-setup.exe`**: a Cloud desktop shell (pywebview) that opens `app.frogswork.com`. There is no separate Local-only installer.

## Prerequisites

- PyInstaller build: `.\client_app\build.ps1 -Clean` → `client_app\dist\FrogsWork\`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (`ISCC.exe`)

## Build

From repo root (normally invoked by `package_client_release.ps1`):

```powershell
.\client_app\scripts\build_installer.ps1 -Version "2.0.0"
```

Output: `client_app\dist\FrogsWork-2.0.0-setup.exe`

Custom PyInstaller folder:

```powershell
.\client_app\scripts\build_installer.ps1 -Version "2.0.0" -AppSource "C:\path\to\FrogsWork"
```

## Script

[`FrogsWork.iss`](FrogsWork.iss) — edit install/uninstall behaviour here.

| Setting | Value |
|---------|--------|
| Default install dir | `{localappdata}\Programs\FrogsWork` |
| What it installs | Shell + WebView2 dependency (Edge WebView2) |
| Publisher / version | KorraOne, version metadata on setup.exe |
| Privileges | `lowest` (no admin) |
| Desktop shortcut | Optional task on install wizard |
| Start at logon | Optional task — shortcut in Startup folder |
| Uninstall Cloud export | `FrogsWork.exe --export-uninstall-data` → same ZIP as Settings → Download my data (when signed in) |
| Stop running app | `taskkill` before uninstall |
| Remove AppData | `{userappdata}\FrogsWork` on uninstall |

## See also

- [DEPLOY.md](../../docs/DEPLOY.md) — upload to R2 and release checklist
- [PLATFORM-ARCHITECTURE.md](../../docs/PLATFORM-ARCHITECTURE.md) — Cloud shell vs PWA hosts
