import { PanelToggle } from "@/components/shell/PanelToggle";
import { HeroScene } from "@/components/visuals/HeroScene";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display tracking-tight">
            Clean E-yAy
          </h1>
          <p className="text-sm text-ink-700-foreground/60">
            v2.0-skeleton · sözleşme tarafından yönlendirilen dashboard
          </p>
        </div>
        <div className="text-xs uppercase tracking-widest text-accent-cyan">
          PAPER_ONLY · NO_EXECUTION
        </div>
      </header>

      <section className="panel relative overflow-hidden">
        <div className="absolute inset-0 -z-10 opacity-70">
          <HeroScene />
        </div>
        <div className="relative">
          <h2 className="text-lg font-medium">Karar Merkezi</h2>
          <p className="text-sm text-white/60 mt-1">
            v2.5-web fazında bu panel `DecisionPanel`'e yerini bırakacak.
            Şimdilik iskelet.
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <PanelToggle
          title="Komuta Sinyalleri"
          views={[
            { id: "cards", label: "Kart" },
            { id: "list", label: "Liste" },
          ]}
        >
          {() => <div className="text-sm text-white/50">v2.5'te bağlanacak.</div>}
        </PanelToggle>

        <PanelToggle
          title="Olay Takvimi"
          views={[
            { id: "3d", label: "3D" },
            { id: "list", label: "Liste" },
          ]}
        >
          {() => <div className="text-sm text-white/50">v2.5'te bağlanacak.</div>}
        </PanelToggle>

        <PanelToggle
          title="Senaryo"
          views={[
            { id: "battle", label: "Battle" },
            { id: "compact", label: "Kompakt" },
          ]}
        >
          {() => <div className="text-sm text-white/50">v2.5'te bağlanacak.</div>}
        </PanelToggle>
      </div>

      <footer className="text-xs text-white/40 pt-8">
        Sözleşme: <code>contracts/openapi.yaml</code> · Tipler codegen ile üretilir.
      </footer>
    </main>
  );
}
