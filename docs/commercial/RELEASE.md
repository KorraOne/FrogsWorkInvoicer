# FrogsWork release and install

How the desktop app is built, installed, updated, and where files live on Windows.

**Production deploy order:** [DEPLOY.md](DEPLOY.md)

## Two separate locations

| Location | What lives there | Updated by |
|----------|------------------|------------|
| **`%LOCALAPPDATA%\Programs\FrogsWork\`** (default install folder) | `FrogsWork.exe` + `_internal\` (the app itself) | Inno Setup install, in-app update, or manual zip replace |
| **`%APPDATA%\FrogsWork\`** | Settings, customers, invoices, billing auth, PDF folder preference | Never touched by app updates |

Your data and account tokens stay in AppData. Updates only replace the program folder.

## Distribution artifacts (two files per version)

| Artifact | Used for | URL pattern |
|----------|----------|-------------|
| **`FrogsWork-x.y.z-setup.exe`** | New installs (marketing download page) | `releases.json` → `download_path` |
| **`FrogsWork-x.y.z-win64.zip`** | In-app updates only | Pi `CLIENT_RELEASE_URL` + `releases.json` → `update_zip_path` |

Both are built by `package_client_release.ps1`. The zip is staged as `FrogsWork\FrogsWork.exe` inside the archive so in-app updates extract cleanly.

## Install layout (PyInstaller onedir)

The build produces a **folder**, not a single portable exe:

```
FrogsWork/
  FrogsWork.exe      ← shortcut points here
  FrogsWork.exe.config
  _internal/         ← required; must stay next to the exe
```

- **Do not** move `FrogsWork.exe` away from `_internal\`. The pair must stay together.
- **Do** move or copy the whole `FrogsWork\` folder if you change install location manually.
- **Shortcuts** (Desktop, Start menu) launch the exe; Inno Setup creates Start menu + optional Desktop shortcut.

### Recommended first-time install (1.1.0+)

1. Download **`FrogsWork-x.y.z-setup.exe`** from https://frogswork.com/download.html
2. Run the installer (default folder: `%LOCALAPPDATA%\Programs\FrogsWork\`)
3. Launch FrogsWork from the Start menu or Desktop shortcut

No zip extraction or first-run relocate step. Requires **Inno Setup 6** on the build machine only (not on end-user PCs).

### Uninstall

From **Settings → Apps → FrogsWork → Uninstall** (or Start menu uninstall entry):

1. Any running FrogsWork process is closed automatically
2. Invoice PDFs are copied silently to `Downloads\FrogsWork-Uninstall-{date}\pdfs\` (see `README.txt` there)
3. Program files are removed from `%LOCALAPPDATA%\Programs\FrogsWork\` (retried if a folder lock delayed deletion)
4. All local data is removed from `%APPDATA%\FrogsWork\`

If the install folder could not be deleted (for example File Explorer had it open), uninstall finishes with one message naming the folder to delete manually.

Implemented via Inno `[UninstallRun]` calling `FrogsWork.exe --export-uninstall-data`, `[UninstallDelete]` for AppData, and installer script cleanup for running processes and leftover program files.

## Build requirements (operator)

| Tool | Purpose |
|------|---------|
| Python 3.13 + `client_app/requirements.txt` | PyInstaller build (via `client_app/build.ps1`) |
| **Inno Setup 6** (`ISCC.exe`) | `FrogsWork-x.y.z-setup.exe` |
| Microsoft Edge **WebView2 Runtime** | Required on target PCs (usually preinstalled on Windows 11) |

Inno Setup: https://jrsoftware.org/isdl.php — installed to `Program Files (x86)\Inno Setup 6\`.

## Distribution (operator workflow)

### 1. Build and package

From repo root:

```powershell
.\scripts\package_client_release.ps1 `
  -Version "1.1.0" `
  -BillingUrl "https://api.frogswork.com" `
  -ReleaseNotes "Windows installer, uninstall PDF export, API connectivity fixes."
```

Outputs:

- `client_app\dist\FrogsWork-1.1.0-setup.exe` — marketing
- `client_app\dist\FrogsWork-1.1.0-win64.zip` — in-app updates
- `marketing_site\releases.json` — download page manifest
- Copies under `marketing_site\downloads\` (upload to R2; do not commit large binaries)

Build only (no installer): `.\client_app\build.ps1 -Clean`

Installer only (after PyInstaller): `.\client_app\scripts\build_installer.ps1 -Version "1.1.0"`

### 2. Upload both files to R2

Bucket host: **https://downloads.frogswork.com**

- `FrogsWork-1.1.0-setup.exe`
- `FrogsWork-1.1.0-win64.zip`

### 3. Enable in-app updates on Pi

In `/etc/frogswork/billing.env` use the **zip** URL and **zip** SHA256 (from the package script output):

```env
CLIENT_RELEASE_VERSION=1.1.0
CLIENT_RELEASE_URL=https://downloads.frogswork.com/FrogsWork-1.1.0-win64.zip
CLIENT_RELEASE_SHA256=<zip sha256 from package script>
CLIENT_RELEASE_NOTES=Windows installer, uninstall PDF export, API connectivity fixes.
```

Restart billing: `sudo systemctl restart frogswork-billing`

Verify: `curl -s https://api.frogswork.com/health` should show `"client_release_version":"1.1.0"`.

### 4. Deploy marketing site

Push updated `marketing_site/releases.json` to `main` (Wrangler redeploys frogswork.com).

`releases.json` fields:

| Field | Purpose |
|-------|---------|
| `download_path` | Setup exe URL (download page button) |
| `setup_sha256` | Optional integrity check for setup |
| `update_zip_path` | Documented zip URL (same as Pi) |
| `sha256` | Zip SHA256 (same as Pi `CLIENT_RELEASE_SHA256`) |

## Who serves what

| Piece | Host |
|-------|------|
| **Setup exe** | `downloads.frogswork.com` (linked from frogswork.com) |
| **Update zip** | `downloads.frogswork.com` (linked from Pi metadata) |
| **Update metadata** | `api.frogswork.com` → `/releases/latest` |
| **Marketing + download page** | `frogswork.com` |

## In-app update flow

When the packaged app reaches the billing API:

1. Checks `/releases/latest` (cached ~1 hour)
2. Shows banner if a newer version exists
3. **Update now** downloads the **zip** from `CLIENT_RELEASE_URL`, verifies SHA256, replaces install folder, restarts

AppData is unchanged. Users who installed via setup.exe still update via zip (same install folder).

## Removing temporary UI

Ship a build with flags off (e.g. `SHOW_LOGO_DESIGN_SETTINGS = False`) via the same release pipeline.
