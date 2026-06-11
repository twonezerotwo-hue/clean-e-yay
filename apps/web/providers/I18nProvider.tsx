"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import en from "@/messages/en.json";
import tr from "@/messages/tr.json";

type Lang = "tr" | "en";
const dicts: Record<Lang, Record<string, string>> = { tr, en };

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
};

const I18nCtx = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("tr");
  const value = useMemo<Ctx>(
    () => ({
      lang,
      setLang,
      t: (key) => dicts[lang]?.[key] ?? key,
    }),
    [lang],
  );
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n(): Ctx {
  const v = useContext(I18nCtx);
  if (!v) throw new Error("I18nProvider missing");
  return v;
}
