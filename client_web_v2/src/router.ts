type Listener = () => void;

export const router = {
  tab: "home",
  sub: null as string | null,
  params: {} as Record<string, string>,

  navigate(tab: string, sub: string | null = null, params: Record<string, string> = {}) {
    this.tab = tab;
    this.sub = sub;
    this.params = params;
    let hash = `#${tab}`;
    if (sub) hash += `/${sub}`;
    if (params.name) hash += `/${encodeURIComponent(params.name)}`;
    if (location.hash !== hash) location.hash = hash;
    listeners.forEach((fn) => fn());
  },

  parseHash() {
    const hash = location.hash || "";
    if (hash.startsWith("#auth/callback")) return;
    const raw = hash.replace(/^#/, "") || "home";
    const parts = raw.split("/").filter(Boolean);
    this.tab = parts[0] || "home";
    this.sub = parts[1] || null;
    this.params = {};
    if (parts[2]) this.params.name = decodeURIComponent(parts.slice(2).join("/"));
  },

  onChange(fn: Listener) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  init() {
    this.parseHash();
    window.addEventListener("hashchange", () => {
      this.parseHash();
      listeners.forEach((fn) => fn());
    });
  },
};

const listeners = new Set<Listener>();

export function setBottomNavActive(tab: string) {
  document.querySelectorAll("#bottom-nav button").forEach((btn) => {
    btn.classList.toggle("active", (btn as HTMLButtonElement).dataset.tab === tab);
  });
}

export function showTabPanels(tab: string) {
  document.querySelectorAll(".tab-panel").forEach((el) => {
    (el as HTMLElement).hidden = (el as HTMLElement).dataset.tab !== tab;
  });
}
