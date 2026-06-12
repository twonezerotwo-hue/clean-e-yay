"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDataSnapshot } from "@/lib/queries/hooks";
import {
  catalystRemainingMinutes,
  selectCatalystImpacts,
} from "@/lib/selectors/catalyst";
import type {
  CatalystActionability,
  CatalystEventType,
  CatalystImpact,
} from "@/types/generated/api";

// v2.7 D5 — Catalyst Impact paneli. Haber → kural tabanlı (deterministik, LLM
// YOK) event_type + asset × timeframe etki haritası + yarı-ömür. Karar etkisi
// YALNIZCA KISITLAYICI (asla size artırmaz); rumor (verified=false) yalnızca
// bağlam. Frontend hesap yapmaz; backend CatalystImpact'ini gösterir.

const EVENT_LABEL: Record<CatalystEventType, string> = {
  geopolitical_deescalation: "Jeopolitik yumuşama",
  geopolitical_escalation: "Jeopolitik tırmanma",
  inflation_data: "Enflasyon verisi",
  jobs_data: "İstihdam verisi",
  central_bank: "Merkez bankası",
  oil_supply: "Petrol arzı",
  oil_inventory: "Petrol stoğu",
  crypto_etf_flow: "Kripto ETF akışı",
  funding_oi_squeeze: "Funding/OI sıkışma",
  earnings: "Bilanço",
  exchange_outage: "Borsa kesintisi",
  rumor_unverified: "Söylenti (doğrulanmamış)",
  unknown: "Bilinmeyen",
};

const ACTION_TONE: Record<CatalystActionability, { label: string; tone: string }> = {
  CONTEXT_ONLY: { label: "yalnızca bağlam", tone: "text-white/40 border-white/10" },
  WATCH: {
    label: "izle",
    tone: "text-accent-cyan/80 border-accent-cyan/30 bg-accent-cyan/5",
  },
  CAUTION: {
    label: "size ×0.5 (CAUTION)",
    tone: "text-orange-300 border-orange-400/40 bg-orange-400/10",
  },
  NO_POSITION_INCREASE: {
    label: "açılış durur (NO_POS_INC)",
    tone: "text-signal-down border-signal-down/40 bg-signal-down/10",
  },
};

function fmtCountdown(min: number | null): string {
  if (min === null) return "—";
  if (min <= 0) return "doldu";
  if (min < 60) return `${min}dk`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h}sa ${m}dk` : `${h}sa`;
}

function CatalystRow({ c }: { c: CatalystImpact }) {
  const action = ACTION_TONE[c.actionability];
  const remaining = catalystRemainingMinutes(c);
  const expired = remaining !== null && remaining <= 0;
  return (
    <li className="border-b border-white/5 pb-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-white/85">
          {EVENT_LABEL[c.event_type]}
        </span>
        <span
          className={`rounded border px-1.5 py-px text-[9px] uppercase tracking-wider ${action.tone}`}
        >
          {action.label}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-white/55 tabular-nums">
        {/* Etkilenen semboller (asset × timeframe etki haritası) */}
        {(c.affected_assets ?? []).map((a) => (
          <span key={a} className="rounded border border-white/10 px-1 py-px font-mono text-white/70">
            {a}
          </span>
        ))}
        {(c.affected_timeframes ?? []).length ? (
          <span className="uppercase tracking-wider text-white/40">
            {(c.affected_timeframes ?? []).join("·")}
          </span>
        ) : null}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-white/45 tabular-nums">
        <span>
          yarı-ömür <span className="text-white/65">{c.expected_half_life_minutes}dk</span>
        </span>
        <span className={expired ? "text-white/30" : "text-accent-cyan/70"}>
          kalan {fmtCountdown(remaining)}
        </span>
        {typeof c.surprise_level === "number" && c.surprise_level !== 0 ? (
          <span className={c.surprise_level > 0 ? "text-signal-up/70" : "text-signal-down/70"}>
            surprise {c.surprise_level > 0 ? "+" : ""}
            {c.surprise_level.toFixed(2)}
          </span>
        ) : null}
        {!c.verified ? (
          <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1 py-px uppercase text-amber-300">
            doğrulanmamış
          </span>
        ) : null}
      </div>
      {(c.evidence ?? []).length ? (
        <div className="mt-1 text-[9px] leading-snug text-white/30">
          {(c.evidence ?? []).slice(0, 2).join(" · ")}
        </div>
      ) : null}
    </li>
  );
}

export function CatalystImpactPanel() {
  const { data } = useDataSnapshot();
  const items = selectCatalystImpacts(data);
  return (
    <PanelFrame id="catalyst_impact">
      <PanelHeader
        title="Catalyst Etkisi"
        subtitle="haber → event_type · yarı-ömür · actionability"
      />
      {!items.length ? (
        <EmptyState />
      ) : (
        <ul className="space-y-2 text-sm max-h-[24rem] overflow-y-auto pr-1">
          {items.map((c) => (
            <CatalystRow key={c.catalyst_id} c={c} />
          ))}
        </ul>
      )}
      <p className="pt-1 text-[9px] leading-snug text-white/30">
        Catalyst kural tabanlıdır (LLM yok). Karar etkisi yalnızca kısıtlayıcı —
        asla size artırmaz; rumor (doğrulanmamış) ve yarı-ömrü dolmuş catalyst
        yalnızca bağlamdır (trade&apos;e dönüşmez). Calendar olayları ayrıdır.
      </p>
    </PanelFrame>
  );
}
