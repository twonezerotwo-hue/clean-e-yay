// apps/web/components/cockpit/CockpitView.tsx
"use client";

import { useCockpitBrief } from "@/lib/queries/hooks";
import { selectAgentBrief, selectDecisionTrace } from "@/lib/selectors/cockpit";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { AgentBrainCard } from "./AgentBrainCard";
import { CockpitCard, buildCockpitCards } from "./cards";
import { SignalRadar } from "./SignalRadar";
import { Layer2QuickNav } from "./Layer2QuickNav";

// KATMAN 1 cockpit — tek useCockpitBrief() çağrısı (tüm kartlar React Query
// cache'inden okur, tekrar fetch yok). Hiçbir karar üretmez; mevcut backend
// ViewModel'ini açıklar ve görselleştirir. PAPER_SAFE / NO_EXECUTION.

export function CockpitView() {
  const { data, isLoading } = useCockpitBrief();

  if (isLoading) {
    return (
      <div className="p-6">
        <LoadingState />
      </div>
    );
  }
  const brief = selectAgentBrief(data);
  if (!brief) {
    return (
      <div className="p-6">
        <EmptyState />
      </div>
    );
  }
  const trace = selectDecisionTrace(data);
  const cards = buildCockpitCards(brief, trace);

  return (
    <main className="mx-auto max-w-7xl px-4 py-5 space-y-5">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-xl font-display text-white/90">Cockpit · Katman 1</h1>
        <span className="text-[10px] uppercase tracking-widest text-white/35">
          Yalnızca okuma · PAPER_SAFE / NO_EXECUTION
        </span>
      </header>

      <AgentBrainCard brief={brief} generatedAt={data?.generated_at} />

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {cards.map((c) => (
          <CockpitCard key={c.id} {...c} />
        ))}
      </section>

      <SignalRadar brief={brief} />

      <Layer2QuickNav />
    </main>
  );
}
