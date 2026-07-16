# FrogsWork PWA v2

Cloud-only mobile app. Built with Vite + TypeScript.

## Dev

```powershell
npm install
npm run dev
```

Open http://localhost:5173 (API defaults to https://api.frogswork.com; local API: set `localStorage.frogswork_api` to `http://127.0.0.1:8787`).

## Deploy

```powershell
npm run build
npx wrangler pages deploy dist --project-name frogswork-app
```

Uses `/mobile/v1/*` API routes (deploy worker after API changes).
