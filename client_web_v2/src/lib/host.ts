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
  }
}

export function isDesktopHost(): boolean {
  return Boolean(window.frogsworkDesktop);
}

export function desktopHostConfig(): FrogsworkDesktopHost | null {
  const host = window.frogsworkDesktop;
  if (!host) return null;
  if (host === true) return {};
  return host;
}

/** Apply body classes and strip PWA install chrome when running in the desktop shell. */
export function applyHostEnvironment(): void {
  if (!isDesktopHost()) return;
  document.body.classList.add("host-desktop");
  document.documentElement.classList.add("host-desktop");
  const manifest = document.querySelector('link[rel="manifest"]');
  if (manifest) manifest.remove();
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
