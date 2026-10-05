"use client";

import { useState } from "react";

import { useDashboardState } from "@/lib/queries/hooks";
import {
  ASSET_TYPE_LABEL,
  CONFIDENCE_LABEL,
  DISCOVERY_STATUS_LABEL,
  discoveryRejectSummary,
  newsArrow,
  shownAssets,
} from "@/lib/selectors/ideas";
import type { NewsDiscoveryAsset, NewsDiscoveryView } from "@/types/generated/api";

function clock(ts?: string | null) {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

/** Dünya Özeti (eski Heart paneli) — Fikirler'in başında tek satır; detay Soul katmanında. */
export function WorldBriefLine() {
  const { data } = useDashboardState();
  const brief = data?.world_brief;
  if (!brief || brief.status === "NO_EVENT") return null;
  return (
    <div className="mb-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
      <div className="text-[9px] uppercase tracking-widest text-accent-cyan/70">Dünya özeti</div>
      <div className="mt-0.5 text-xs text-white/85">{brief.title}</div>
      <div className="text-[11px] leading-5 text-white/55">{brief.summary}</div>
    </div>
  );
}

function AssetChip({ asset }: { asset: NewsDiscoveryAsset }) {
  const up = asset.direction === "up";
  const tone = up ? "border-emerald-400/30 text-emerald-200" : "border-red-400/30 text-red-200";
  const typeLabel = asset.status === "registry" ? "takipte" : ASSET_TYPE_LABEL[asset.asset_type ?? ""] ?? "";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border bg-black/20 px-1.5 py-0.5 text-[10px] ${tone}`}
      title={`${asset.name ?? ""} · güven ${CONFIDENCE_LABEL[asset.confidence ?? ""] ?? "?"}${
        asset.mechanism ? ` · ${asset.mechanism}` : ""
      }`}
    >
      {newsArrow(asset.direction ?? undefined)} {asset.symbol}
      {typeLabel ? <span className="text-white/35">{typeLabel}</span> : null}
    </span>
  );
}

/** Haber akışından keşif: olay → sonuç → etkilenen varlıklar (doğrulanmış). */
export function NewsDiscoverySection({ vm }: { vm?: NewsDiscoveryView }) {
  const [all, setAll] = useState(false);
  const events = vm?.events ?? [];
  const shown = all ? events : events.slice(0, 5);
  const rejected = discoveryRejectSummary(vm);

  return (
    <div className="mb-3 rounded-lg border border-accent-cyan/15 bg-[#03101b]/70 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[10px] uppercase tracking-widest text-accent-cyan/80">Haber akışından keşif</div>
        <div className="text-[10px] text-white/40">
          {DISCOVERY_STATUS_LABEL[vm?.status ?? "UNKNOWN"] ?? vm?.status} · bugün {vm?.stats?.calls_today ?? 0} YZ
          taraması · havuz {vm?.stats?.pool ?? 0} başlık
        </div>
      </div>
      {!events.length ? (
        <div className="mt-2 text-[11px] text-white/40">
          Henüz doğrulanmış etki yok — yerel YZ her öğrenme turunda yeni başlıkları tarar.
        </div>
      ) : (
        <ul className="mt-2 space-y-2">
          {shown.map((ev) => (
            <li key={`${ev.title}-${ev.analyzed_at}`} className="text-[11px] leading-5">
              <div className="text-white/80">
                {ev.title}
                <span className="ml-1 text-[10px] text-white/35">
                  {ev.source} {clock(ev.ts)}
                </span>
              </div>
              {ev.consequence ? <div className="text-white/55">→ {ev.consequence}</div> : null}
              <div className="mt-1 flex flex-wrap gap-1">
                {shownAssets(ev).map((a) => (
                  <AssetChip key={`${a.symbol}-${a.direction}`} asset={a} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-white/35">
        <span>
          YZ önerir, sembol Yahoo&apos;da doğrulanır{rejected ? ` · elenen öneriler: ${rejected}` : ""}.
        </span>
        {events.length > 5 ? (
          <button type="button" onClick={() => setAll((v) => !v)} className="uppercase tracking-widest text-accent-cyan/70 hover:text-accent-cyan">
            {all ? "daha az" : `tümü (${events.length})`}
          </button>
        ) : null}
      </div>
    </div>
  );
}
