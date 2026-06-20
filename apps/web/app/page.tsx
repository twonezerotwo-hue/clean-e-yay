import { CockpitView } from "@/components/cockpit/CockpitView";
import { AgentBriefingPanel } from "@/components/panels/AgentBriefingPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";

export default function HomePage() {
  return (
    <div className="bg-[#05070b]">
      <div className="mx-auto max-w-7xl px-4 pt-5">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <AgentBriefingPanel />
          </div>
          <div className="lg:col-span-1">
            <ChatPanel />
          </div>
        </div>
      </div>
      <CockpitView />
    </div>
  );
}
