"use client";

import { useState, type ReactNode } from "react";

/**
 * Aynı konuyu gösteren panelleri tek kutuda sekmeli toplar (temizlik F4 / K8).
 * Paneller değişmez; yalnız aynı anda biri görünür. Seçilmeyen sekme mount
 * edilmez (gereksiz istek atmaz).
 */
export type TabbedBoxTab = { key: string; label: string; node: ReactNode };

export function TabbedBox({ tabs, initial }: { tabs: TabbedBoxTab[]; initial?: string }) {
  const [active, setActive] = useState(initial ?? tabs[0]?.key);
  const current = tabs.find((t) => t.key === active) ?? tabs[0];
  if (!current) return null;
  return (
    <div className="min-w-0">
      <div role="tablist" className="mb-2 flex flex-wrap gap-1.5">
        {tabs.map((t) => {
          const on = t.key === current.key;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setActive(t.key)}
              className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] transition ${
                on
                  ? "border-accent-cyan/45 bg-accent-cyan/15 text-accent-cyan"
                  : "border-white/10 bg-white/[0.03] text-white/50 hover:text-white/75"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel">{current.node}</div>
    </div>
  );
}
