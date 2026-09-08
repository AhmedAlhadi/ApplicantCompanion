import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
export type ThemePref = "system" | Theme;

const KEY = "ac-theme";

function getStoredPref(): ThemePref {
  const v = localStorage.getItem(KEY);
  return v === "light" || v === "dark" ? v : "system";
}

function getSystemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function resolveTheme(pref: ThemePref = getStoredPref()): Theme {
  return pref === "system" ? getSystemTheme() : pref;
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

type Listener = (theme: Theme) => void;
const listeners = new Set<Listener>();

function notify(theme: Theme) {
  applyTheme(theme);
  listeners.forEach((l) => l(theme));
}

export function setThemePref(pref: ThemePref) {
  if (pref === "system") localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, pref);
  notify(resolveTheme(pref));
}

/** Current resolved theme plus the user's preference. Follows OS changes while pref is "system". */
export function useTheme(): { theme: Theme; pref: ThemePref; setPref: (p: ThemePref) => void } {
  const [theme, setTheme] = useState<Theme>(() => resolveTheme());
  const [pref, setPref] = useState<ThemePref>(() => getStoredPref());

  useEffect(() => {
    applyTheme(theme);
    const listener: Listener = (t) => setTheme(t);
    listeners.add(listener);
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onOsChange = () => {
      if (getStoredPref() === "system") notify(getSystemTheme());
    };
    mq.addEventListener("change", onOsChange);
    return () => {
      listeners.delete(listener);
      mq.removeEventListener("change", onOsChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    theme,
    pref,
    setPref: (p: ThemePref) => {
      setPref(p);
      setThemePref(p);
    },
  };
}
