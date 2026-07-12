# macOS desktop (deferred)

macOS packaging is **deferred** until after Cloud PWA and Windows dual-mode ship.

When built, macOS will follow the same model as Windows:

| Tier | Storage |
|------|---------|
| Local | `~/Library/Application Support/FrogsWork/` per Mac |
| Cloud | Document API + optional local cache |

Planned work (not started):

- `build.sh` + PyInstaller darwin spec
- `.app` bundle, codesign/notarize, DMG
- `app_platform` path/dialog glue for Finder reveal
- Release artifacts in `releases.json` + R2

See the cloud roadmap plan for execution order (Phase 6).
