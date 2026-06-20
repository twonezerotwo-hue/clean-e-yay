"use client";

/**
 * Haberler & Catalyst — 3 sekme: Haberler · Catalyst · Olay Takvimi.
 *
 * Mevcut NewsPanel + CatalystImpactPanel + EventCalendarPanel'i sekme içeriği
 * olarak yükler. Eski paneller silinmedi — registry'de duruyor, DETAY'da
 * ayrı kullanılabilir.
 */
import { useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { CatalystImpactPanel } from "@/components/panels/CatalystImpactPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";

type Tab = "news" | "catalyst" | "calendar";

const TABS: { id: Tab; label: string }[] = [
  { id: "news",     label: "Haberler" },
  { id: "catalyst", label: "Catalyst" },
  { id: "calendar", label: "Olay Takvimi" },
];

export function HaberlerCatalystPanel() {
  const [tab, setTab] = useState<Tab>("news");

  return (
    <div data-testid="haberler-catalyst" className="space-y-2">
      <div className="flex items-center gap-1 px-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-md border px-2 py-1 text-[11px] font-mono uppercase tracking-widest transition-colors ${
              tab === t.id
                ? "border-accent-cyan/60 text-accent-cyan bg-accent-cyan/10"
                : "border-white/10 text-white/40 hover:text-white/70"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "news" && <NewsPanel />}
      {tab === "catalyst" && <CatalystImpactPanel />}
      {tab === "calendar" && <EventCalendarPanel />}
    </div>
  );
}
