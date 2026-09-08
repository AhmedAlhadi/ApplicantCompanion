import { useEffect, useState } from "react";
import type { AppLanguage } from "../api/types";
import { ar } from "../locales/ar";
import { en } from "../locales/en";

export type { AppLanguage };

const UI_KEY = "ac-ui-language";
const CONTENT_KEY = "ac-content-language";
const DEFAULT_LANGUAGE: AppLanguage = "ar";

type Dict = { [key: string]: string | readonly string[] | string[] | Dict };

const catalogs: Record<AppLanguage, Dict> = { ar: ar as Dict, en: en as Dict };

type Listener = (lang: AppLanguage) => void;
const listeners = new Set<Listener>();

function isLanguage(value: string | null): value is AppLanguage {
  return value === "ar" || value === "en";
}

export function getUiLanguage(): AppLanguage {
  if (typeof localStorage === "undefined") return DEFAULT_LANGUAGE;
  const stored = localStorage.getItem(UI_KEY);
  return isLanguage(stored) ? stored : DEFAULT_LANGUAGE;
}

export function getContentLanguage(): AppLanguage {
  if (typeof localStorage === "undefined") return DEFAULT_LANGUAGE;
  const stored = localStorage.getItem(CONTENT_KEY);
  return isLanguage(stored) ? stored : DEFAULT_LANGUAGE;
}

export function applyUiLanguage(lang: AppLanguage) {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

export function setUiLanguage(lang: AppLanguage) {
  localStorage.setItem(UI_KEY, lang);
  applyUiLanguage(lang);
  listeners.forEach((fn) => fn(lang));
}

export function setContentLanguage(lang: AppLanguage) {
  localStorage.setItem(CONTENT_KEY, lang);
}

function lookup(dict: Dict, key: string): unknown {
  let cur: unknown = dict;
  for (const part of key.split(".")) {
    if (!cur || typeof cur !== "object" || Array.isArray(cur) || !(part in (cur as object))) {
      return undefined;
    }
    cur = (cur as Dict)[part];
  }
  return cur;
}

function interpolate(value: string, vars?: Record<string, string | number>): string {
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (_, name: string) =>
    vars[name] === undefined ? `{${name}}` : String(vars[name]),
  );
}

export function t(key: string, vars?: Record<string, string | number>): string {
  const primary = lookup(catalogs[getUiLanguage()], key);
  const fallback = lookup(catalogs.en, key);
  const value = typeof primary === "string" ? primary : typeof fallback === "string" ? fallback : key;
  return interpolate(value, vars);
}

export function tList(key: string): string[] {
  const primary = lookup(catalogs[getUiLanguage()], key);
  if (Array.isArray(primary)) return [...primary];
  const fallback = lookup(catalogs.en, key);
  return Array.isArray(fallback) ? [...fallback] : [];
}

export function dateLocale(): string {
  return getUiLanguage() === "ar" ? "ar" : "en";
}

export function formatDate(value: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(dateLocale(), options);
}

export function useT() {
  const [lang, setLang] = useState<AppLanguage>(() => getUiLanguage());

  useEffect(() => {
    applyUiLanguage(lang);
    const listener: Listener = (next) => setLang(next);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, [lang]);

  return {
    t,
    tList,
    lang,
    setLang: setUiLanguage,
    contentLanguage: getContentLanguage(),
    setContentLanguage,
  };
}
