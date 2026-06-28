# FrogsWork (client_app)

Commercial desktop sales invoicing app. Forked from [`../invoice_app/`](../invoice_app/). **No Python imports** from the grandparents app.

- **Product name:** FrogsWork
- **Repo folder:** `client_app/`
- **Build output:** `FrogsWork.exe`
- **Entry:** `app.py` (+ `desktop_shell.py` for windowed mode)
- **AppData:** `%APPDATA%\FrogsWork\`

## Docs

[`../docs/commercial/README.md`](../docs/commercial/README.md) · [naming conventions](../docs/commercial/naming.md)

## Dev

```powershell
# From repo root
.\scripts\dev-test.ps1 -Action StartAll
```

## Build

```powershell
.\build_client.ps1
```
