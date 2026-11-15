// Display settings: theme, panel order, text size. Saved per browser in localStorage.
export type Theme = "dark" | "light" | "system";
export type Layout = "results-middle" | "agent-middle";
export type TextSize = "s" | "m" | "l";
export type Settings = { theme: Theme; layout: Layout; text: TextSize };

export const DEFAULTS: Settings = { theme: "dark", layout: "agent-middle", text: "m" };
const KEY = "parallax-settings";

export function loadSettings(): Settings {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return { ...DEFAULTS, ...raw };
  } catch {
    return DEFAULTS;
  }
}

export function saveSettings(s: Settings) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode or storage disabled: settings just won't persist */
  }
}

export function resolveTheme(t: Theme): "dark" | "light" {
  if (t !== "system") return t;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applySettings(s: Settings) {
  const root = document.documentElement;
  root.dataset.theme = resolveTheme(s.theme);
  root.dataset.text = s.text;
}

// Runs before the page paints, so a saved light/dark choice doesn't flash the other theme first.
export const PRELOAD_SCRIPT = `(function(){try{var s=JSON.parse(localStorage.getItem("${KEY}")||"{}");var t=s.theme||"${DEFAULTS.theme}";if(t==="system")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t;document.documentElement.dataset.text=s.text||"${DEFAULTS.text}";}catch(e){document.documentElement.dataset.theme="${DEFAULTS.theme}";}})();`;

// Panel widths, as shares of the page per panel (so swapping panel order keeps each panel's size).
export type PanelSizes = { map: number; results: number; agent: number };
export const DEFAULT_SIZES: PanelSizes = { map: 0.37, results: 0.30, agent: 0.33 };
const SIZE_KEY = "parallax-panels";
export const MIN_SHARE = 0.16;

export function loadSizes(): PanelSizes {
  try {
    const s = JSON.parse(window.localStorage.getItem(SIZE_KEY) || "null");
    if (s && s.map > 0 && s.results > 0 && s.agent > 0) return s;
  } catch { /* fall through */ }
  return DEFAULT_SIZES;
}

export function saveSizes(s: PanelSizes) {
  try { window.localStorage.setItem(SIZE_KEY, JSON.stringify(s)); } catch { /* not saved */ }
}
