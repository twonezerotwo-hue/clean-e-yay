import { CockpitView } from "@/components/cockpit/CockpitView";
import { AgentBriefingPanel } from "@/components/panels/AgentBriefingPanel";

export default function HomePage() {
  return (
    <div className="bg-[#05070b]">
      <div className="mx-auto max-w-7xl px-4 pt-5">
        <AgentBriefingPanel />
      </div>
      <CockpitView />
    </div>
  );
}
