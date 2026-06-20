// apps/web/components/cockpit/cards.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { PanelFrame } from "@/components/shell/PanelFrame";
import type { AgentBrief, DecisionTrace } from "@/types/generated/api";

// KATMAN 1 — 7 ana kart. Hepsi backend ViewModel'inden (agent_brief +
// decision_trace) okunur. DOMAIN HESABI YOK: değerler ve anlamlar backend'den;
// burada yalnızca alan seçimi + sabit Türkçe açıklama + ton + Katman 2 nav var.

export type CardTone = "ok" | "info" | "watch" | "caution" | "critical";

const TONE_DOT: Record<CardTone, string> = {
  ok: "bg-signal-up",
  info: "bg-white/40",
  watch: "bg-accent-cyan",
  caution: "bg-amber-400",
  critical: "bg-signal-down",
};
const TONE_TEXT: Record<CardTone, string> = {
  ok: "text-signal-up",
  info: "text-white/80",
  watch: "text-accent-cyan",
  caution: "text-amber-400",
  critical: "text-signal-down",
};

export type CockpitCardProps = {
  id: string;
  title: string;
  tone: CardTone;
  value: string;
  status: string;
  meaning: string; // Anlamı
  reason: string; // Neden / Etki
  watch: string[]; // Neye bakmalı
  detailHref: string; // birincil Katman 2 hedefi
  detailLabel: string;
  relatedHrefs?: { label: string; href: string }[];
};

// Varsayılan yüz = renk + değer + tek satır anlam (10 sn). Detay tap arkasında.
export function CockpitCard(p: CockpitCardProps) {
  const [open, setOpen] = useState(false);
  return (
    <PanelFrame id={`layer1_${p.id}`}>
      <button onClick={() => setOpen((o) => !o)} className="w-full text-left" aria-expanded={open}>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${TONE_DOT[p.tone]}`} />
          <span className="text-[10px] uppercase tracking-widest text-white/40">{p.title}</span>
        </div>
        <div className={`mt-1 text-lg font-display leading-tight ${TONE_TEXT[p.tone]}`}>
          {p.value}
        </div>
        <div className="text-[11px] text-white/55">{p.status}</div>
        <p className="mt-1.5 text-xs text-white/75 leading-snug">{p.meaning}</p>
        <span className="mt-1 inline-block text-[10px] text-accent-cyan/60">
          {open ? "− detayı gizle" : "+ neden / neye bakmalı"}
        </span>
      </button>

      {open ? (
        <div className="mt-2 space-y-2 border-t border-white/10 pt-2">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-white/40">Neden / Etki</div>
            <p className="text-xs text-white/75 leading-snug">{p.reason}</p>
          </div>
          {p.watch.length ? (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-white/40">Neye bakmalı</div>
              <ul className="text-xs text-white/70 space-y-0.5 mt-0.5">
                {p.watch.map((w, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-accent-cyan/70">›</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Link
              href={p.detailHref}
              className="rounded border border-accent-cyan/30 bg-accent-cyan/5 px-2 py-0.5 text-[11px] text-accent-cyan/90 hover:bg-accent-cyan/10"
            >
              {p.detailLabel} →
            </Link>
            {p.relatedHrefs?.map((r, i) => (
              <Link
                key={i}
                href={r.href}
                className="rounded border border-white/15 px-2 py-0.5 text-[11px] text-white/60 hover:text-white"
              >
                {r.label}
              </Link>
            ))}
          </div>
        </div>
      ) : null}
    </PanelFrame>
  );
}

// ── Katman 2 hedefleri ──────────────────────────────────────────────────────
// NOT: Katman 2 tek sayfalık panel dashboard'u (/dashboard). Derin link için
// panel id'leri panel-registry.ts ile doğrulanır. Yanlış id'de en kötü
// /dashboard'a düşer.
const L2 = (panelId: string) => `/dashboard#${panelId}`;
const T = {
  decision: { href: L2("decision_trace"), label: "Decision & Evidence" },
  risk: { href: L2("risk_gate"), label: "Risk & Execution" },
  data: { href: L2("data_quality"), label: "Data Quality & Providers" },
  assets: { href: L2("agent_matrix"), label: "Assets & Timeframes" },
  macro: { href: L2("catalyst_impact"), label: "Macro, Catalyst & News" },
  structure: { href: L2("correlation"), label: "Market Structure" },
  paper: { href: L2("paper_action"), label: "Paper & Learning" },
  ops: { href: L2("replay_status"), label: "Ops & Replay" },
};

function blockerTarget(code: string) {
  if (code === "RISK_GATE") return T.risk;
  if (code === "DQS_BLOCKED" || code === "PROVIDER_DOWN") return T.data;
  return T.decision;
}
function statusTone(status: string): CardTone {
  switch (status) {
    case "ACTIONABLE": return "ok";
    case "WATCHING": return "watch";
    case "FROZEN": return "caution";
    case "BLOCKED": return "critical";
    default: return "info";
  }
}
function dataTone(mode: string): CardTone {
  if (mode === "LIVE_VERIFIED") return "ok";
  if (mode === "LIVE_DEGRADED") return "watch";
  if (mode === "BLOCKED") return "critical";
  return "caution";
}

export function buildCockpitCards(
  b: AgentBrief,
  trace: DecisionTrace | undefined,
): CockpitCardProps[] {
  const can = b.can_act;
  const gates = trace?.restrictive_gates ?? [];
  const structureGates = gates.filter((g) =>
    ["Derivatives", "Volatility", "Options", "Correlation"].includes(g),
  );
  const ps = b.paper_state_summary ?? {};
  const cands = b.top_candidates ?? [];

  // 1) DECISION (Final Decision + Main Blocker birleşik — karar A)
  const bt = blockerTarget(b.main_blocker.code);
  const decision: CockpitCardProps = {
    id: "decision",
    title: "Decision",
    tone: statusTone(b.status),
    value: can ? "İŞLEM AÇILABİLİR" : "YENİ İŞLEM YOK",
    status: `Durum: ${b.status}`,
    meaning: can
      ? "RiskGate limitleri dahilinde yeni giriş açılabilir."
      : "Sistem şu an yeni işlem açmıyor.",
    reason:
      b.main_blocker.code === "NONE"
        ? "Risk kapısı açık, aktif engel yok."
        : `Ana engel: ${b.main_blocker.label}. ${b.main_blocker.detail ?? ""}`.trim(),
    watch:
      b.next_watch_conditions?.slice(0, 3).map((w) => w.label) ?? [
        "RiskGate açılıyor mu?",
        "Aday skorları yükseliyor mu?",
      ],
    detailHref: bt.href,
    detailLabel: bt.label,
  };

  // 2) RISKGATE
  const riskAction = b.risk?.action ?? null;
  const restrictive = riskAction !== null && !["HOLD", "WATCH"].includes(riskAction);
  const risk: CockpitCardProps = {
    id: "risk_gate",
    title: "RiskGate",
    tone: restrictive ? "caution" : "ok",
    value: b.risk?.action ?? "—",
    status: b.main_blocker.code === "RISK_GATE" ? "Yeni giriş kapalı" : "Kapı durumu",
    meaning:
      "Sistem mevcut pozisyonları izleyebilir ama RiskGate kısıtı varsa yeni pozisyon açmaz.",
    reason:
      b.risk?.reason ??
      "Yaklaşan kritik olay, DQS problemi, drawdown veya catalyst riski kapıyı kısabilir.",
    watch: ["RiskGate OPEN oldu mu?", "Event riski geçti mi?", "Drawdown / kill switch aktif mi?"],
    detailHref: T.risk.href,
    detailLabel: T.risk.label,
  };

  // 3) DATA TRUST
  const dqsScore = b.dqs?.score;
  const data: CockpitCardProps = {
    id: "data_trust",
    title: "Data Trust",
    tone: dataTone(b.data_mode),
    value: `DQS ${dqsScore != null ? Math.round(dqsScore) : "—"} · ${b.dqs?.status ?? "—"}`,
    status: `Mod: ${b.data_mode}`,
    meaning: "Kararların dayandığı verinin güven seviyesi.",
    reason:
      "Freshness, completeness, drift ve sağlayıcı durumundan oluşur. Düşükse karar daha temkinli okunur; eksik sağlayıcı varsa live güven sınırlanır.",
    watch: [
      "DQS OK → DEGRADED oldu mu?",
      "Sağlayıcılar (FRED, coingecko, yfinance) düzeldi mi?",
      "Kritik veri eksiği giderildi mi?",
    ],
    detailHref: T.data.href,
    detailLabel: T.data.label,
  };

  // 4) TOP CANDIDATES
  const topc: CockpitCardProps = {
    id: "top_candidates",
    title: "Top Candidates",
    tone: cands.some((c) => c.actionable) ? "ok" : "info",
    value: cands.length
      ? cands.slice(0, 3).map((c) => `${c.symbol ?? "?"} ${Math.round(c.score ?? 0)}`).join(" · ")
      : "aday yok",
    status: `${cands.length} aday · aday ≠ trade`,
    meaning: "Radardaki en güçlü ham adaylar. Aday sinyal final trade değildir.",
    reason:
      "RiskGate kapalıysa veya skor actionable değilse işlem açılmaz. Raw signal ile final trade aynı şey değil.",
    watch: [
      "Skor 60+ üzerine çıkıyor mu?",
      "neutral → bullish/bearish netleşiyor mu?",
      "RiskGate açılınca yeniden değerlendiriliyor mu?",
    ],
    detailHref: T.assets.href,
    detailLabel: T.assets.label,
  };

  // 5) MACRO / CATALYST
  const macro: CockpitCardProps = {
    id: "macro_catalyst",
    title: "Macro / Catalyst",
    tone: "info",
    value: b.regime ?? "—",
    status: "Rejim + catalyst",
    meaning: "Dış dünya koşulları sisteme ne yaptırıyor?",
    reason:
      "Makro rejim risk almaya uygun olsa bile yaklaşan kritik olay (FOMC, CPI, NFP) yeni girişleri kapatabilir.",
    watch: [
      "FOMC / CPI / NFP / jeopolitik risk var mı?",
      "Catalyst etkisi sönüyor mu?",
      "Rejim OFFENSIVE / NEUTRAL / RISK-OFF mu?",
    ],
    detailHref: T.macro.href,
    detailLabel: T.macro.label,
  };

  // 6) MARKET STRUCTURE
  const structure: CockpitCardProps = {
    id: "market_structure",
    title: "Market Structure",
    tone: structureGates.length ? "caution" : "ok",
    value: structureGates.length ? structureGates.join(" · ") : "temiz",
    status: structureGates.length ? "Kısıt aktif" : "Yapı temiz",
    meaning: "Piyasanın iç yapısı (türev, funding, OI, volatilite, opsiyon, korelasyon).",
    reason:
      "Bu veriler trade açtırmaz; sadece riski küçültür, pozisyon boyutunu sınırlar veya sistemi temkinli yapar.",
    watch: [
      "Put skew / term stress arttı mı?",
      "Volatilite shock veya squeeze var mı?",
      "Correlation cluster riski var mı?",
    ],
    detailHref: T.structure.href,
    detailLabel: T.structure.label,
  };

  // 7) PAPER & SYSTEM
  const paper: CockpitCardProps = {
    id: "paper_system",
    title: "Paper & System",
    tone: ps.frozen ? "critical" : "ok",
    value: `${ps.open_positions ?? b.open_paper_positions ?? 0} açık pozisyon`,
    status: ps.new_entries_disabled ? "Yeni giriş kapalı" : "Aktif",
    meaning: "Sistem paper modda ne yapıyor ve teknik olarak sağlıklı mı?",
    reason: ps.frozen
      ? "Sistem donduruldu — owner reset gerekli."
      : "Açık pozisyon, time-stop, paper aksiyon ve sağlık durumu burada özetlenir.",
    watch: [
      ps.expired_time_stops ? `${ps.expired_time_stops} time-stop süresi doldu` : "Yeni snapshot geldi mi?",
      "Worker stale düzeldi mi?",
      "Learning için yeterli kapalı trade var mı?",
    ],
    detailHref: T.paper.href,
    detailLabel: T.paper.label,
    relatedHrefs: [{ label: "Ops & Replay", href: T.ops.href }],
  };

  return [decision, risk, data, topc, macro, structure, paper];
}
