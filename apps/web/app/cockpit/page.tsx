import { CockpitView } from "@/components/cockpit/CockpitView";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";

// Layer 1 route. The default home page renders the same CockpitView;
// the Layer 2 detail dashboard stays under /dashboard.
export default function CockpitPage() {
  return (
    <ErrorBoundary
      fallback={
        <main className="grid min-h-screen place-items-center bg-[#02030a] p-6 text-white">
          <div className="max-w-sm rounded-lg border border-red-400/30 bg-red-950/20 p-5 text-center">
            <h1 className="font-display text-lg text-red-100">Cockpit render hatasi</h1>
            <p className="mt-2 text-sm leading-6 text-white/62">
              Mobil tarayicida bir client hatasi yakalandi. Sayfayi yenileyince tekrar denenir.
            </p>
          </div>
        </main>
      }
    >
      <CockpitView />
    </ErrorBoundary>
  );
}
