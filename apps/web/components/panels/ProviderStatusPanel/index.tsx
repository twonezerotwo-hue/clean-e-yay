"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectProviderList } from "@/lib/selectors/snapshot";
import { fmtRelative } from "@/lib/format";

const STATUS_COLOR: Record<string, string> = {
  ok: "bg-signal-up/20 text-signal-up",
  degraded: "bg-amber-400/20 text-amber-400",
  down: "bg-signal-down/20 text-signal-down",
  unknown: "bg-white/10 text-white/40",
};

export function ProviderStatusPanel() {
  const { data, isLoading } = useDataSnapshot();
  if (isLoading) {
    return (
      <PanelFrame id="provider_status">
        <PanelHeader title="Sağlayıcı Durumu" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const providers = selectProviderList(data);
  if (!providers.length) {
    return (
      <PanelFrame id="provider_status">
        <PanelHeader title="Sağlayıcı Durumu" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="provider_status">
      <PanelHeader
        title="Sağlayıcı Durumu"
        subtitle={`${providers.length} sağlayıcı`}
      />
      <ul className="space-y-1.5 text-xs">
        {providers.map((p) => (
          <li
            key={p.name}
            className="flex items-center justify-between border-b border-white/5 pb-1"
          >
            <span className="font-medium uppercase tracking-wide">{p.name}</span>
            <span className="flex items-center gap-2">
              <span
                className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
                  STATUS_COLOR[p.status] ?? STATUS_COLOR.unknown
                }`}
              >
                {p.status}
              </span>
              <span className="text-white/40 tabular-nums">
                {p.calls} çağrı
              </span>
              {p.fallbacks > 0 ? (
                <span className="text-signal-down">{p.fallbacks} fallback</span>
              ) : null}
              <span className="text-white/40">{fmtRelative(p.last_success_at)}</span>
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
