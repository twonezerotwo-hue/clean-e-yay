// apps/web/app/cockpit/page.tsx
import { CockpitView } from "@/components/cockpit/CockpitView";

// KATMAN 1 rotası: /cockpit. Mevcut Katman 2 (app/page.tsx) DOKUNULMADI.
// Layer 1'i varsayılan ana ekran yapmak istersen: bu içeriği app/page.tsx'e
// taşı, mevcut dashboard'u app/dashboard/page.tsx'e al (tek satırlık reroute).

export default function CockpitPage() {
  return <CockpitView />;
}
