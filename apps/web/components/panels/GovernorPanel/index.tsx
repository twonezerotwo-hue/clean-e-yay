"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useGovernorReport } from "@/lib/queries/hooks";
import type { GovernorReport } from "@/types/generated/api";

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

// Governor = owner'ın onay masası: öneri defteri + diğer onay bekleyenler + veri
// güveni. (Kendi kendine görev üreten döngü temizlikte söküldü — K, 2026-10-02.)
export function GovernorPanel() {
  const { data, isLoading } = useGovernorReport();

  if (isLoading) {
    return (
      <PanelFrame id="governor">
        <PanelHeader title="Sistem Yöneticisi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d = data as GovernorReport | undefined;
  const proposals = rec(d?.proposals?.data);
  const other = rec(d?.other_pending_approvals?.data);
  const trust = rec(d?.data_trust?.data);
  const providers = rec(trust.providers);
  const dqs = rec(trust.dqs);

  const pendingCount = num(proposals.pending_count) ?? 0;
  const degraded = num(providers.degraded_count);
  const dqsStatus = typeof dqs.status === "string" ? dqs.status : null;
  const otherPending = [
    other.weights === true ? "ağırlık önerisi" : null,
    other.tf_targets === true ? "TF hedef önerisi" : null,
    other.mode_overrides_active === true ? "aktif mod geçersiz kılma" : null,
  ].filter((x): x is string => x !== null);

  return (
    <PanelFrame id="governor">
      <PanelHeader
        title="Sistem Yöneticisi"
        subtitle="Onayını bekleyenler ve veri güveni — işlem açmaz, ayar değiştirmez"
      />

      <div className="grid grid-cols-3 gap-2">
        <Stat label="Bekleyen öneri" value={String(pendingCount)} tone={pendingCount > 0 ? "warn" : undefined} />
        <Stat
          label="Veri güveni"
          value={dqsStatus ?? "—"}
          tone={degraded != null && degraded > 0 ? "warn" : undefined}
        />
        <Stat label="Degraded provider" value={degraded == null ? "—" : String(degraded)} />
      </div>

      {otherPending.length > 0 ? (
        <div className="mt-2 rounded border border-amber-400/25 bg-amber-400/8 px-2 py-1.5 text-[11px] text-white/70">
          <span className="uppercase tracking-widest text-white/40">Ayrıca onay bekliyor: </span>
          {otherPending.join(", ")}
        </div>
      ) : null}
    </PanelFrame>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn";
}) {
  return (
    <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-center">
      <div
        className={`text-sm font-semibold tabular-nums ${
          tone === "warn" ? "text-amber-300" : "text-white/80"
        }`}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-white/45">{label}</div>
    </div>
  );
}
