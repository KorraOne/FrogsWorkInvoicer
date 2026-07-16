const listeners = new Set();

export const router = {
  tab: "home",
  sub: null,
  params: {},

  navigate(tab, sub = null, params = {}) {
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

  onChange(fn) {
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

export function setBottomNavActive(tab) {
  document.querySelectorAll("#bottom-nav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
}

export function showTabPanels(tab) {
  document.querySelectorAll(".tab-panel").forEach((el) => {
    el.hidden = el.dataset.tab !== tab;
  });
}
