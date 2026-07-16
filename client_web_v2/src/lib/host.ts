/** Host detection for browser / PWA vs pywebview desktop shell. */

export type FrogsworkDesktopHost = {
  /** Override API base (e.g. staging). */
  apiBase?: string;
  /** Open URL in the system browser (injected by the shell). */
  openExternal?: (url: string) => void;
};

declare global {
  interface Window {
    frogsworkDesktop?: FrogsworkDesktopHost | true;
    pywebview?: {
      api?: {
        open_external?: (url: string) => unknown;
        get_api_base?: () => string;
      };
    };
  }
}

function syncFromPywebviewApi(): FrogsworkDesktopHost | null {
  const api = window.pywebview?.api;
  if (!api) return null;
  const host: FrogsworkDesktopHost = {
    openExternal: (url: string) => {
      if (api.open_external) api.open_external(url);
    },
  };
  try {
    const base = api.get_api_base?.();
    if (base) host.apiBase = String(base).replace(/\/$/, "");
  } catch {
    /* ignore */
  }
  window.frogsworkDesktop = host;
  return host;
}

export function isDesktopHost(): boolean {
  return Boolean(window.frogsworkDesktop) || Boolean(window.pywebview);
}

export function desktopHostConfig(): FrogsworkDesktopHost | null {
  if (window.frogsworkDesktop && window.frogsworkDesktop !== true) {
    return window.frogsworkDesktop;
  }
  const fromApi = syncFromPywebviewApi();
  if (fromApi) return fromApi;
  if (window.frogsworkDesktop === true || window.pywebview) return {};
  return null;
}

/** Apply body classes and strip PWA install chrome when running in the desktop shell. */
export function applyHostEnvironment(): void {
  if (!isDesktopHost()) return;
  document.body.classList.add("host-desktop");
  document.documentElement.classList.add("host-desktop");
  const manifest = document.querySelector('link[rel="manifest"]');
  if (manifest) manifest.remove();
  syncFromPywebviewApi();
}

/** Prefer the system browser for http(s) links when the shell provides openExternal. */
export function openExternalUrl(url: string): boolean {
  const cfg = desktopHostConfig();
  if (cfg?.openExternal && /^https?:\/\//i.test(url)) {
    try {
      cfg.openExternal(url);
      return true;
    } catch {
      /* fall through */
    }
  }
  return false;
}

/** Wire clicks on http(s) anchors to the system browser when in the desktop shell. */
export function wireExternalLinks(root: ParentNode = document): void {
  root.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const anchor = target.closest("a[href]") as HTMLAnchorElement | null;
    if (!anchor) return;
    const href = anchor.getAttribute("href") || "";
    if (!/^https?:\/\//i.test(href)) return;
    if (openExternalUrl(href)) {
      event.preventDefault();
    }
  });
}

/** Listen for late pywebviewready so host classes apply even if the event fires after boot. */
export function watchPywebviewReady(): void {
  if (!window.pywebview) {
    window.addEventListener("pywebviewready", () => {
      syncFromPywebviewApi();
      applyHostEnvironment();
    });
  }
}
