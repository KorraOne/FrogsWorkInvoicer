# FrogsWork release and install

How the desktop app is built, installed, updated, and where files live on Windows.

**Production deploy order:** [DEPLOY.md](DEPLOY.md)

## Two separate locations

| Location | What lives there | Updated by |
|----------|------------------|------------|
| **`%LOCALAPPDATA%\Programs\FrogsWork\`** (recommended install folder) | `FrogsWork.exe` + `_internal\` (the app itself) | In-app update or manual zip replace |
| **`%APPDATA%\FrogsWork\`** | Settings, customers, invoices, billing auth, PDF folder preference | Never touched by app updates |

Your data and account tokens stay in AppData. Updates only replace the program folder.

## Install layout (PyInstaller onedir)

The build produces a **folder**, not a single portable exe:

```
FrogsWork/
  FrogsWork.exe      ← shortcut points here
  _internal/         ← required; must stay next to the exe
```

- **Do not** move `FrogsWork.exe` away from `_internal\`. The pair must stay together.
- **Do** move or copy the whole `FrogsWork\` folder if you change install location.
- **Shortcuts** (Desktop, Start menu, taskbar pin) can live anywhere; they only launch the exe.

### Recommended first-time install

1. Download from https://frogswork.com/download.html
2. Extract the whole folder to `%LOCALAPPDATA%\Programs\FrogsWork\`
3. Run `FrogsWork.exe`

This path is user-writable, so in-app updates work without administrator rights.

## Distribution (operator workflow)

### 1. Build and package

```powershell
.\scripts\package_client_release.ps1 `
  -Version "1.0.0" `
  -BillingUrl "https://api.frogswork.com" `
  -ReleaseNotes "First public release."
```

### 2. Upload zip to R2

`https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip`

### 3. Enable updates on Pi

In `/etc/frogswork/billing.env`:

```env
CLIENT_RELEASE_VERSION=1.0.0
CLIENT_RELEASE_URL=https://downloads.frogswork.com/FrogsWork-1.0.0-win64.zip
CLIENT_RELEASE_SHA256=<from package script>
CLIENT_RELEASE_NOTES=First public release.
```

Restart billing: `sudo systemctl restart frogswork-billing`

### 4. Deploy marketing site

Push updated `marketing_site/releases.json` to Cloudflare Pages.

## Who serves what

| Piece | Host |
|-------|------|
| **Zip file** | `downloads.frogswork.com` |
| **Update metadata** | `api.frogswork.com` → `/releases/latest` |
| **Marketing + download page** | `frogswork.com` |

## In-app update flow

When the packaged app reaches the billing API:

1. Checks `/releases/latest` (cached ~1 hour)
2. Shows banner if a newer version exists
3. **Update now** downloads from `CLIENT_RELEASE_URL`, verifies SHA256, replaces install folder, restarts

AppData is unchanged.

## Removing temporary UI

Ship a build with flags off (e.g. `SHOW_LOGO_DESIGN_SETTINGS = False`) via the same release pipeline.
