import { CockpitView } from "@/components/cockpit/CockpitView";

// Layer 1 route. The default home page renders the same CockpitView;
// the Layer 2 detail dashboard stays under /dashboard.
export default function CockpitPage() {
  return <CockpitView />;
}
