// apps/web/components/cockpit/Layer2QuickNav.tsx
"use client";

import Link from "next/link";

// KATMAN 1 → KATMAN 2 hızlı geçiş. Hedefler app/page.tsx (tek sayfalık panel
// dashboard) + panel hash'i. Panel id'leri panel-registry.ts ile doğrulanmalı;
// yanlış id'de en kötü Katman 2 ana sayfasına düşülür.

const NAV: { label: string; panelId: string }[] = [
  { label: "Decision & Evidence", panelId: "decision_trace" },
  { label: "Risk & Execution", panelId: "risk_gate" },
  { label: "Assets & Timeframes", panelId: "agent_matrix" },
  { label: "Data Quality & Providers", panelId: "data_quality" },
  { label: "Macro, Catalyst & News", panelId: "catalyst_impact" },
  { label: "Market Structure", panelId: "correlation" },
  { label: "Scenario & Alerts", panelId: "scenario" },
  { label: "Paper & Learning", panelId: "paper_action" },
  { label: "Ops & Replay", panelId: "replay_status" },
];

export function Layer2QuickNav() {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-white/40 mb-2">
        Katman 2 — detay ekranları
      </div>
      <div className="flex flex-wrap gap-2">
        {NAV.map((n) => (
          <Link
            key={n.panelId}
            href={`/#${n.panelId}`}
            className="rounded-lg border border-white/12 bg-white/[0.03] px-3 py-1.5 text-xs text-white/70 hover:border-accent-cyan/40 hover:text-white transition-colors"
          >
            {n.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
