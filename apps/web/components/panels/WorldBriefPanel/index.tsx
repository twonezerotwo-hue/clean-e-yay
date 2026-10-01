"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { useDashboardState } from "@/lib/queries/hooks";
import type { WorldBrief } from "@/types/generated/api";

type Props = { detail?: boolean };

function statusTone(status: WorldBrief["status"]): string {
  if (status === "OK") return "text-signal-up";
  if (status === "UNAVAILABLE") return "text-signal-down";
  return "text-amber-300";
}

function listValues(values: string[] | undefined, empty = "yok") {
  return values?.length ? values.join(" · ") : empty;
}

export function WorldBriefPanel({ detail = false }: Props) {
  const { data, isLoading } = useDashboardState();
  const brief = data?.world_brief;

  return (
    <PanelFrame id="world_brief" className="border-accent-cyan/20">
      <PanelHeader
        title="Dünya Özeti"
        subtitle={detail ? "kanıt → etki → tahmin / narrative-only" : "LLM yönetici özeti / read-only"}
        actions={
          brief ? (
            <span className={`rounded border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] uppercase tracking-widest ${statusTone(brief.status)}`}>
              {brief.source} · {brief.status}
            </span>
          ) : null
        }
      />
      {isLoading ? <LoadingState /> : !brief ? <EmptyState message="Dünya özeti henüz hazır değil." /> : (
        <div className="space-y-3">
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent-cyan/75">
                {brief.trigger ?? "WORLD_STATE"}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-white/40">
                {brief.execution}
              </div>
            </div>
            <h3 className="mt-2 text-sm font-medium text-white/90">{brief.title}</h3>
            <p className="mt-1 text-xs leading-5 text-white/65">{brief.summary}</p>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <InfoLine label="Etkilenen varlıklar" value={listValues(brief.affected_assets, "eşleşme yok")} />
            <InfoLine label="Aksiyon durumu" value={brief.actionability} tone={brief.actionability === "OBSERVE_ONLY" ? "text-amber-300" : "text-white/70"} />
          </div>

          {detail ? (
            <>
              <InfoLine label="Neden önemli" value={brief.why_it_matters ?? "Backend kanıtı yok."} />
              <InfoLine label="İzlenecekler" value={listValues(brief.what_to_watch)} />
              <InfoLine label="Geçersiz kılan kanıt" value={listValues(brief.invalidators)} />
              <EvidenceRows brief={brief} />
            </>
          ) : null}
        </div>
      )}
    </PanelFrame>
  );
}

function InfoLine({ label, value, tone = "text-white/65" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-1 text-xs leading-5 ${tone}`}>{value}</div>
    </div>
  );
}

function EvidenceRows({ brief }: { brief: WorldBrief }) {
  const forecasts = brief.forecast_bands ?? [];
  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">Backend kanıtı</div>
      <div className="grid gap-2 lg:grid-cols-2">
        <InfoLine label="Kullanılan kanıt" value={listValues(brief.evidence_used)} />
        <InfoLine label="Eksik veri" value={listValues(brief.missing_data)} />
      </div>
      {forecasts.length ? (
        <div className="overflow-x-auto rounded-lg border border-white/10 bg-black/20">
          <table className="w-full text-left text-[10px]">
            <thead className="text-white/38">
              <tr>
                <th className="px-3 py-2 font-medium">Varlık / ufuk</th>
                <th className="px-3 py-2 font-medium">Yön</th>
                <th className="px-3 py-2 font-medium">p10 · p50 · p90</th>
                <th className="px-3 py-2 font-medium">Durum</th>
              </tr>
            </thead>
            <tbody>
              {forecasts.map((row, index) => (
                <tr key={`${String(row.symbol ?? "?")}-${String(row.horizon ?? index)}`} className="border-t border-white/5 text-white/65">
                  <td className="px-3 py-2 font-mono text-white/80">{String(row.symbol ?? "?")} · {String(row.horizon ?? "?")}</td>
                  <td className="px-3 py-2">{String(row.directional_bias ?? "UNKNOWN")}</td>
                  <td className="px-3 py-2 font-mono">{String(row.p10 ?? "—")} · {String(row.p50 ?? "—")} · {String(row.p90 ?? "—")}</td>
                  <td className="px-3 py-2">{row.available ? "AVAILABLE" : "MISSING_DATA"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

