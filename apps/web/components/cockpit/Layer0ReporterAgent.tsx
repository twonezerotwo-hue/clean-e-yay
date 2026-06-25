"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  useAgentBriefing,
  useChat,
  useDataSnapshot,
  useClosePaperPosition,
  usePaperTradingState,
} from "@/lib/queries/hooks";
import { api } from "@/lib/api/client";
import { selectDqs, selectSnapshotMeta } from "@/lib/selectors/snapshot";
import type { AgentBriefing, ChatResponse, Position } from "@/types/generated/api";
import {
  Layer0HumanComputerModel,
  type Layer0DataQualityPulse,
} from "./Layer0HumanComputerModel";

type ReporterMessage = {
  role: "user" | "agent";
  text: string;
  meta?: ChatResponse;
};

type SpeechRecognitionResultLike = {
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  results: {
    [index: number]: SpeechRecognitionResultLike;
    length: number;
  };
};

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type ExecutiveBriefing = {
  tone: string;
  stance_label: string;
  headline: string;
  narrative: string;
  recommendation: string;
  flags?: string[];
};

type BriefingEngine = {
  stale?: boolean;
  age_seconds?: number | null;
};

type AgentBriefingWithExecutive = AgentBriefing & {
  executive?: ExecutiveBriefing | null;
  engine?: BriefingEngine | null;
};

/** Center "ilk ekran" karar paneli için CockpitView'den gelen hazır veriler. */
type ScanState = "OK" | "IZLE" | "ENGEL";
type ScanItem = { label: string; value: string; ok: boolean; state?: ScanState; href?: string };
export type Layer0HeroProps = {
  title: string;
  detail: string;
  tone: string;
  status: { label: string; tone: string };
  dqs: { value: string; tone: string };
  candidates: number;
  positions: number;
  scans: { veri: ScanItem; risk: ScanItem; sinyal: ScanItem; ticket: ScanItem };
  watch: { key: string; label: string }[];
};

const QUICK_PROMPTS = [
  "15 dakikalik firsat var mi?",
  "Son 1 saat haberlerini ozetle.",
  "Neden islem yok?",
  "Isleme en yakin aday hangisi?",
  "Risk tarafinda beni ne engelliyor?",
  "Bana 30 saniyelik piyasa brifingi ver.",
];

const CATEGORY_LABEL: Record<string, string> = {
  market: "Piyasa",
  agent: "Agent",
  risk: "Risk",
  events: "Olay",
  news: "Haber",
  providers: "Saglayici",
  alerts: "Bildirim",
  system: "Sistem",
};

function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null) return "bilinmiyor";
  if (seconds < 90) return `${Math.round(seconds)} sn`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} dk`;
  return `${(seconds / 3600).toFixed(1)} sa`;
}
function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scopedWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return scopedWindow.SpeechRecognition ?? scopedWindow.webkitSpeechRecognition ?? null;
}

function cleanForVoice(text: string) {
  return text
    .replace(/\s+/g, " ")
    .replace(/[•·]/g, ".")
    .trim()
    .slice(0, 900);
}

function shortLine(text: string, max = 148) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}...` : clean;
}

function fmtMoney(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return "---";
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function fmtSignedMoney(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "---";
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}$${fmtMoney(value)}`;
}

function fmtPrice(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "---";
  const digits = Math.abs(value) >= 100 ? 2 : 4;
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function numericDraft(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "";
  return String(value);
}

function normalizeDecimalInput(value: string) {
  return value.replace(",", ".").replace(/[^\d.-]/g, "");
}

function positionSideLabel(side: Position["side"]) {
  return side === "long" ? "LONG" : "SHORT";
}

function positionPnlTone(value: number | null | undefined) {
  if (value == null) return "text-white/62";
  return value >= 0 ? "text-emerald-300" : "text-red-300";
}

function statusText(value: string | null | undefined) {
  return value ? value.replace(/_/g, " ") : "---";
}

function Layer0PositionManager({
  positions,
  totalPnl,
  loading,
}: {
  positions: Position[];
  totalPnl: number;
  loading: boolean;
}) {
  const closePosition = useClosePaperPosition();
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  const totalSize = useMemo(
    () => positions.reduce((sum, position) => sum + (position.size_usd ?? 0), 0),
    [positions],
  );
  const missingSl = useMemo(
    () => positions.filter((position) => position.sl == null).length,
    [positions],
  );
  const missingTp = useMemo(
    () => positions.filter((position) => position.tp == null).length,
    [positions],
  );

  useEffect(() => {
    setExpandedIds((current) => {
      const validIds = new Set(positions.map((position) => position.id));
      const next = new Set([...current].filter((id) => validIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [positions]);

  const toggleExpanded = (positionId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(positionId)) {
        next.delete(positionId);
      } else {
        next.add(positionId);
      }
      return next;
    });
  };

  return (
    <div className="layer0-card layer0-position-center relative flex min-h-0 flex-1 flex-col overflow-hidden border-accent-cyan/20 bg-[radial-gradient(circle_at_82%_10%,rgba(34,211,238,0.12),transparent_34%),linear-gradient(180deg,rgba(3,12,24,0.88),rgba(2,6,13,0.96))] shadow-[0_0_54px_rgba(34,211,238,0.08),inset_0_1px_0_rgba(255,255,255,0.05)]">
      <div className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-accent-cyan/45 to-transparent" />
      <div className="relative flex items-start justify-between gap-3 border-b border-accent-cyan/10 pb-3">
        <div>
          <div className="text-[15px] font-semibold uppercase tracking-[0.18em] text-white/88">
            Açık Pozisyonlar
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-widest text-white/36">
            paper-safe pozisyon yönetim merkezi
          </div>
        </div>
        <div className="rounded-full border border-white/10 bg-white/[0.035] px-2.5 py-1 text-[9px] font-semibold uppercase tracking-widest text-white/42">
          PAPER_SAFE
        </div>
      </div>

      <div className="relative mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        <PositionMetric label="Açık" value={loading ? "..." : String(positions.length)} />
        <PositionMetric
          label="Açık P&L"
          value={loading ? "..." : fmtSignedMoney(totalPnl)}
          tone={positionPnlTone(totalPnl)}
        />
        <PositionMetric label="Büyüklük" value={loading ? "..." : `$${fmtMoney(totalSize)}`} />
        <PositionMetric label="SL eksik" value={loading ? "..." : String(missingSl)} tone={missingSl ? "text-amber-200" : "text-emerald-300"} />
        <PositionMetric label="TP eksik" value={loading ? "..." : String(missingTp)} tone={missingTp ? "text-amber-200" : "text-emerald-300"} />
      </div>

      <div className="relative mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
        {positions.length ? (
          <div className="space-y-1.5">
            {positions.map((position) => (
              <PositionCard
                key={position.id}
                position={position}
                expanded={expandedIds.has(position.id)}
                onToggle={() => toggleExpanded(position.id)}
                onManage={() => setSelectedPosition(position)}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-3 text-sm text-white/50">
            Açık pozisyon yok. Bu alan sadece mevcut backend paper state'inden gelen açık pozisyonları gösterir.
          </div>
        )}
      </div>

      {selectedPosition ? (
        <PositionManageModal
          position={selectedPosition}
          closePosition={closePosition}
          onClose={() => setSelectedPosition(null)}
        />
      ) : null}
    </div>
  );
}

function PositionMetric({
  label,
  value,
  tone = "text-white/88",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-accent-cyan/15 bg-cyan-950/20 px-2 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]">
      <div className="text-[8px] uppercase tracking-[0.18em] text-white/34">{label}</div>
      <div className={`mt-0.5 truncate font-mono text-[13px] font-bold tabular-nums ${tone}`}>
        {value}
      </div>
    </div>
  );
}

function PositionCard({
  position,
  expanded,
  onToggle,
  onManage,
}: {
  position: Position;
  expanded: boolean;
  onToggle: () => void;
  onManage: () => void;
}) {
  const pnl = position.unrealized_pnl_usd ?? 0;
  const isLong = position.side === "long";
  const accentClass = isLong
    ? "border-emerald-300/25 bg-[radial-gradient(circle_at_0%_0%,rgba(16,185,129,0.13),transparent_36%),linear-gradient(135deg,rgba(4,18,18,0.88),rgba(1,7,13,0.94))] shadow-[0_0_22px_rgba(16,185,129,0.08),inset_0_1px_0_rgba(255,255,255,0.04)]"
    : "border-rose-300/30 bg-[radial-gradient(circle_at_0%_0%,rgba(244,63,94,0.14),transparent_36%),linear-gradient(135deg,rgba(20,6,16,0.88),rgba(1,7,13,0.94))] shadow-[0_0_22px_rgba(244,63,94,0.08),inset_0_1px_0_rgba(255,255,255,0.04)]";
  const badgeClass = isLong
    ? "border-emerald-300/35 bg-emerald-300/10 text-emerald-200 shadow-[0_0_16px_rgba(16,185,129,0.14)]"
    : "border-rose-300/35 bg-rose-300/10 text-rose-200 shadow-[0_0_16px_rgba(244,63,94,0.14)]";

  return (
    <article
      onClick={onToggle}
      className={`group cursor-pointer rounded-xl border p-2.5 transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 ${accentClass}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-bold text-white/94">{position.symbol}</span>
            <span
              className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest ${badgeClass}`}
            >
              {positionSideLabel(position.side)}
            </span>
            <span className="rounded border border-accent-cyan/30 bg-accent-cyan/10 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-accent-cyan/80">
              {String(position.timeframe ?? "--").toUpperCase()}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <PositionMiniValue label="Entry" value={fmtPrice(position.entry_price)} />
            <PositionMiniValue label="Current" value={fmtPrice(position.current_price)} />
            <PositionMiniValue label="Size" value={`$${fmtMoney(position.size_usd)}`} />
          </div>
        </div>
        <div className="text-right">
          <div className={`font-mono text-base font-black tabular-nums ${positionPnlTone(pnl)}`}>
            {fmtSignedMoney(pnl)}
          </div>
          <div className="mt-0.5 text-[9px] uppercase tracking-widest text-white/32">Açık P&L</div>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggle();
          }}
          className="rounded-lg border border-white/10 bg-white/[0.035] px-2.5 py-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-white/46 transition-colors hover:border-accent-cyan/30 hover:text-accent-cyan"
        >
          {expanded ? "Detay Kapat" : "Detay"}
        </button>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onManage();
          }}
          className="rounded-lg border border-accent-cyan/30 bg-accent-cyan/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-cyan transition-colors hover:border-accent-cyan/50 hover:bg-accent-cyan/20"
        >
          Yönet
        </button>
      </div>

      {expanded ? (
        <div className="mt-2 border-t border-white/[0.07] pt-2">
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            <PositionField label="SL" value={fmtPrice(position.sl)} tone={position.sl == null ? "text-amber-200" : "text-white/76"} />
            <PositionField label="TP" value={fmtPrice(position.tp)} tone={position.tp == null ? "text-amber-200" : "text-white/76"} />
            <PositionField label="Lifecycle" value={statusText(position.lifecycle_status)} />
            <PositionField label="Time-stop" value={statusText(position.time_stop_status)} />
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 text-[9px] uppercase tracking-widest">
            <span className="rounded border border-white/10 bg-white/[0.03] px-2 py-1 text-white/38">
              PAPER_SAFE
            </span>
            <span className="min-w-0 truncate font-mono text-white/30">
              ID {position.id}
            </span>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function PositionMiniValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-white/[0.06] bg-black/18 px-2 py-1">
      <div className="text-[8px] uppercase tracking-[0.16em] text-white/30">{label}</div>
      <div className="mt-0.5 truncate font-mono text-[11px] font-semibold tabular-nums text-white/74">
        {value}
      </div>
    </div>
  );
}

function PositionField({
  label,
  value,
  tone = "text-white/68",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-white/[0.06] bg-white/[0.025] px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-[0.18em] text-white/30">{label}</div>
      <div className={`mt-0.5 truncate font-mono text-[11px] tabular-nums ${tone}`}>
        {value}
      </div>
    </div>
  );
}

function PositionManageModal({
  position,
  closePosition,
  onClose,
}: {
  position: Position;
  closePosition: ReturnType<typeof useClosePaperPosition>;
  onClose: () => void;
}) {
  const [slDraft, setSlDraft] = useState(numericDraft(position.sl));
  const [tpDraft, setTpDraft] = useState(numericDraft(position.tp));
  const [actionOpen, setActionOpen] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSlDraft(numericDraft(position.sl));
    setTpDraft(numericDraft(position.tp));
    setActionOpen(false);
    setConfirmClose(false);
    setNotice(null);
    setError(null);
  }, [position]);

  const fullClose = () => {
    if (!confirmClose) {
      setConfirmClose(true);
      setNotice("Tam kapatma için ikinci onay gerekiyor.");
      return;
    }
    setError(null);
    closePosition.mutate(position.id, {
      onSuccess: () => {
        setNotice("Pozisyon kapatma isteği backend'e iletildi.");
        onClose();
      },
      onError: (mutationError) => {
        const message =
          mutationError instanceof Error
            ? mutationError.message
            : "Pozisyon kapatma başarısız oldu.";
        setError(message);
      },
    });
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center bg-black/62 p-3 backdrop-blur-sm sm:items-center">
      <div className="max-h-[92dvh] w-full max-w-2xl overflow-hidden rounded-2xl border border-accent-cyan/20 bg-[#040b14]/95 shadow-[0_28px_90px_rgba(0,0,0,0.55),0_0_60px_rgba(34,211,238,0.13)]">
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] px-4 py-3">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.2em] text-white/88">
              Pozisyon Yönet
            </div>
            <div className="mt-1 text-[11px] uppercase tracking-widest text-accent-cyan/70">
              {position.symbol} · {positionSideLabel(position.side)} · {position.timeframe ?? "--"}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-white/[0.035] text-white/58 transition-colors hover:border-white/22 hover:text-white"
            aria-label="Kapat"
          >
            ×
          </button>
        </div>

        <div className="max-h-[calc(92dvh-64px)] overflow-y-auto p-4">
          <div className="grid gap-2 sm:grid-cols-3">
            <PositionMetric label="Entry" value={fmtPrice(position.entry_price)} />
            <PositionMetric label="Current" value={fmtPrice(position.current_price)} />
            <PositionMetric label="Size" value={`$${fmtMoney(position.size_usd)}`} />
            <PositionMetric
              label="P&L"
              value={fmtSignedMoney(position.unrealized_pnl_usd)}
              tone={positionPnlTone(position.unrealized_pnl_usd)}
            />
            <PositionMetric label="SL" value={fmtPrice(position.sl)} tone={position.sl == null ? "text-amber-200" : "text-white/88"} />
            <PositionMetric label="TP" value={fmtPrice(position.tp)} tone={position.tp == null ? "text-amber-200" : "text-white/88"} />
          </div>

          {position.lifecycle_status ? (
            <div className="mt-3 rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-[11px] uppercase tracking-widest text-white/42">
              lifecycle: <span className="text-white/72">{statusText(position.lifecycle_status)}</span>
            </div>
          ) : null}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-[10px] uppercase tracking-[0.18em] text-white/40">
                Stop Loss
              </span>
              <input
                value={slDraft}
                onChange={(event) => setSlDraft(normalizeDecimalInput(event.target.value))}
                inputMode="decimal"
                placeholder="örn. 63800.5"
                className="w-full rounded-xl border border-white/10 bg-black/28 px-3 py-2 font-mono text-sm text-white/86 outline-none transition-colors focus:border-accent-cyan/45"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-[10px] uppercase tracking-[0.18em] text-white/40">
                Take Profit
              </span>
              <input
                value={tpDraft}
                onChange={(event) => setTpDraft(normalizeDecimalInput(event.target.value))}
                inputMode="decimal"
                placeholder="örn. 67250"
                className="w-full rounded-xl border border-white/10 bg-black/28 px-3 py-2 font-mono text-sm text-white/86 outline-none transition-colors focus:border-accent-cyan/45"
              />
            </label>
          </div>

          <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100/72">
            SL/TP güncelleme endpoint'i backend'de hazır olduğunda aktifleşecek.
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled
              className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/32"
            >
              Risk Planı Kaydet
            </button>
            <button
              type="button"
              onClick={() => {
                setSlDraft(numericDraft(position.entry_price));
                setNotice("Break-even SL alanına yazıldı. Kaydetmek için backend risk-plan endpoint'i gerekir.");
                setConfirmClose(false);
              }}
              className="rounded-xl border border-emerald-300/30 bg-emerald-300/10 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-200 transition-colors hover:border-emerald-300/40"
            >
              Break-even
            </button>
            <div className="relative">
              <button
                type="button"
                onClick={() => setActionOpen((value) => !value)}
                className="rounded-xl border border-red-300/30 bg-red-300/10 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-red-200 transition-colors hover:border-red-300/40"
              >
                Kapat / Azalt
              </button>
              {actionOpen ? (
                <div className="absolute bottom-full left-0 z-10 mb-2 w-64 overflow-hidden rounded-xl border border-white/10 bg-[#050b14] shadow-2xl">
                  <button
                    type="button"
                    disabled
                    className="block w-full px-3 py-2 text-left text-xs text-white/30"
                  >
                    %25 azalt
                    <span className="mt-0.5 block text-[10px] text-white/24">
                      Partial close backend endpoint bekleniyor.
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled
                    className="block w-full border-t border-white/[0.06] px-3 py-2 text-left text-xs text-white/30"
                  >
                    %50 azalt
                    <span className="mt-0.5 block text-[10px] text-white/24">
                      Partial close backend endpoint bekleniyor.
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={fullClose}
                    disabled={closePosition.isPending}
                    className="block w-full border-t border-white/[0.06] px-3 py-2 text-left text-xs font-semibold text-red-200 transition-colors hover:bg-red-400/10 disabled:opacity-50"
                  >
                    {closePosition.isPending
                      ? "Kapatılıyor..."
                      : confirmClose
                        ? "Onayla"
                        : "Tamamını kapat"}
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          {notice ? (
            <div className="mt-3 rounded-xl border border-accent-cyan/20 bg-accent-cyan/10 px-3 py-2 text-xs text-accent-cyan/80">
              {notice}
            </div>
          ) : null}
          {error ? (
            <div className="mt-3 rounded-xl border border-red-300/20 bg-red-400/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Layer 0 orta sutundaki karar, metrik ve tarama HUD'u. */
function Layer0StatusCore({
  hero,
  onNavigate,
}: {
  hero: Layer0HeroProps;
  onNavigate: (layer: 0 | 1 | 2 | 3) => void;
}) {
  const metrics = [
    { label: "Durum", value: hero.status.label, tone: hero.status.tone },
    { label: "DQS", value: hero.dqs.value, tone: hero.dqs.tone },
    { label: "Aday", value: String(hero.candidates), tone: "text-emerald-200" },
    { label: "Pozisyon", value: String(hero.positions), tone: "text-amber-200" },
  ];
  const nodes = [
    { key: "veri", item: hero.scans.veri, index: "01", onClick: () => onNavigate(3) },
    { key: "risk", item: hero.scans.risk, index: "02" },
    { key: "sinyal", item: hero.scans.sinyal, index: "03", onClick: () => onNavigate(1) },
    { key: "ticket", item: hero.scans.ticket, index: "04" },
  ];

  return (
    <div className="layer0-status-core shrink-0">
      <div className="layer0-status-core__scan" aria-hidden />
      <div className="layer0-status-core__head">
        <div className="min-w-0">
          <div className="layer0-status-core__kicker">Canli karar cekirdegi</div>
          <div className={`layer0-status-core__title ${hero.tone}`}>{hero.title}</div>
          <div className="layer0-status-core__detail">{hero.detail}</div>
        </div>
        <div className="layer0-status-core__mode">
          <span>MOD</span>
          <strong>{hero.status.label}</strong>
        </div>
      </div>

      <div className="layer0-status-core__metrics">
        {metrics.map((metric) => (
          <div key={metric.label} className="layer0-status-metric">
            <span>{metric.label}</span>
            <strong className={metric.tone}>{metric.value}</strong>
          </div>
        ))}
      </div>

      <div className="layer0-status-core__nodes">
        {nodes.map(({ key, item, index, onClick }) => {
          const state = item.state ?? (item.ok ? "OK" : "IZLE");
          const cls = `layer0-status-node ${
            state === "OK"
              ? "layer0-status-node--ok"
              : state === "ENGEL"
                ? "layer0-status-node--block"
                : "layer0-status-node--watch"
          }`;
          const content = (
            <>
              <span className="layer0-status-node__pulse" aria-hidden />
              <span className="layer0-status-node__index">{index}</span>
              <span className="layer0-status-node__copy">
                <strong>{item.label}</strong>
                <em>{item.value}</em>
              </span>
              <span className="layer0-status-node__state">{state}</span>
            </>
          );
          if (item.href) {
            return (
              <a key={key} href={item.href} className={cls}>
                {content}
              </a>
            );
          }
          return (
            <button key={key} type="button" onClick={onClick} className={cls}>
              {content}
            </button>
          );
        })}
      </div>

      {hero.watch.length ? (
        <div className="layer0-status-core__watch">
          {hero.watch.slice(0, 2).map((item) => (
            <div key={item.key} className="layer0-status-watch">
              <span aria-hidden />
              <p>{item.label}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function Layer0ReporterAgent({
  hero,
  onNavigate,
}: {
  hero: Layer0HeroProps;
  onNavigate: (layer: 0 | 1 | 2 | 3) => void;
}) {
  const briefing = useAgentBriefing();
  const chat = useChat();
  const paper = usePaperTradingState();
  const snapshot = useDataSnapshot();
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [messages, setMessages] = useState<ReporterMessage[]>([]);
  const [input, setInput] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [dialogueMode, setDialogueMode] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [micReady, setMicReady] = useState(false);
  const [lastUserText, setLastUserText] = useState("");
  const [streamedText, setStreamedText] = useState("");
  const dialogueModeRef = useRef(false);
  const listeningRef = useRef(false);
  const chatPendingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const speechRunRef = useRef(0);

  useEffect(() => {
    setMicReady(Boolean(getSpeechRecognition()));
    return () => {
      speechRunRef.current += 1;
      audioRef.current?.pause();
      audioRef.current = null;
      if (audioUrlRef.current) {
        window.URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      setSpeaking(false);
      setVoiceLoading(false);
      recognitionRef.current?.stop();
    };
  }, []);

  useEffect(() => {
    dialogueModeRef.current = dialogueMode;
  }, [dialogueMode]);

  useEffect(() => {
    listeningRef.current = listening;
  }, [listening]);

  useEffect(() => {
    chatPendingRef.current = chat.isPending;
  }, [chat.isPending]);

  const briefingData = briefing.data as AgentBriefingWithExecutive | undefined;
  const executive = briefingData?.executive ?? null;

  const briefingText = useMemo(() => {
    if (executive) {
      return `${executive.headline} ${executive.narrative} Tavsiyem: ${executive.recommendation}`;
    }
    const headlines = briefingData?.headlines ?? [];
    if (!headlines.length) return "Briefing bekleniyor. Bir sonraki veri cycle'i okunuyor.";
    return headlines
      .slice(0, 4)
      .map((item) => `${CATEGORY_LABEL[item.category] ?? item.category}: ${item.title}`)
      .join(". ");
  }, [briefingData?.headlines, executive]);

  const activeExchange = useMemo(() => {
    let agentIndex = -1;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index]?.role === "agent") {
        agentIndex = index;
        break;
      }
    }

    const questionSearchLimit = agentIndex >= 0 ? agentIndex : messages.length;
    let userIndex = -1;
    for (let index = questionSearchLimit - 1; index >= 0; index -= 1) {
      if (messages[index]?.role === "user") {
        userIndex = index;
        break;
      }
    }

    const pendingUserIndex =
      agentIndex < 0 && messages[messages.length - 1]?.role === "user" ? messages.length - 1 : -1;

    return {
      agent: agentIndex >= 0 ? messages[agentIndex] : null,
      agentIndex,
      user: userIndex >= 0 ? messages[userIndex] : pendingUserIndex >= 0 ? messages[pendingUserIndex] : null,
      userIndex: userIndex >= 0 ? userIndex : pendingUserIndex,
    };
  }, [messages]);

  const latestAgentText = useMemo(() => {
    return activeExchange.agent?.text ?? briefingText;
  }, [activeExchange.agent?.text, briefingText]);

  const dataQualityPulse = useMemo<Layer0DataQualityPulse | null>(() => {
    const dqs = selectDqs(snapshot.data);
    if (!dqs) return null;
    const meta = selectSnapshotMeta(snapshot.data);
    const generatedAt = meta?.generated_at ? Date.parse(meta.generated_at) : NaN;
    const ageSeconds = Number.isFinite(generatedAt)
      ? Math.max(0, (Date.now() - generatedAt) / 1000)
      : null;
    return {
      score: dqs.score,
      status: dqs.status,
      freshness: dqs.freshness,
      completeness: dqs.completeness,
      drift: dqs.drift,
      reconciliation: dqs.reconciliation,
      decisionUsage: dqs.decision_usage,
      ageLabel: ageSeconds == null ? "snapshot bekleniyor" : `${fmtAge(ageSeconds)} önce`,
    };
  }, [snapshot.data]);

  const clearAudioPlayback = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      window.URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  };

  const speakWithBrowserFallback = (text: string) => {
    if (!voiceEnabled || typeof window === "undefined" || !("speechSynthesis" in window)) {
      return false;
    }
    clearAudioPlayback();
    window.speechSynthesis.cancel();
    setSpeaking(false);
    const utterance = new SpeechSynthesisUtterance(cleanForVoice(text));
    utterance.lang = "tr-TR";
    utterance.rate = 1.0;
    utterance.pitch = 1.02;
    const voices = window.speechSynthesis.getVoices();
    // Doğal/neural sesleri tercih et (Microsoft "Online (Natural)", Google,
    // wavenet…) — yoksa varsayılan robotik sese düş.
    const isNatural = (v: SpeechSynthesisVoice) =>
      /natural|neural|online|google|premium|wavenet|siri/i.test(v.name);
    const isTr = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().startsWith("tr");
    const isEn = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().startsWith("en");
    utterance.voice =
      voices.find((v) => isTr(v) && isNatural(v)) ??
      voices.find(isTr) ??
      voices.find((v) => isEn(v) && isNatural(v)) ??
      voices.find(isEn) ??
      null;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => {
      setSpeaking(false);
      if (dialogueModeRef.current) {
        window.setTimeout(() => startListening(), 520);
      }
    };
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    return true;
  };

  const speak = async (text: string) => {
    const cleanText = cleanForVoice(text);
    if (!voiceEnabled || !cleanText || typeof window === "undefined") {
      return false;
    }

    const runId = speechRunRef.current + 1;
    speechRunRef.current = runId;
    setVoiceError(null);
    setVoiceLoading(true);
    setSpeaking(false);
    clearAudioPlayback();
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    try {
      const audioBlob = await api.voiceSpeak({ text: cleanText });
      if (speechRunRef.current !== runId) return false;

      const audioUrl = window.URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audioUrlRef.current = audioUrl;
      audio.onended = () => {
        if (speechRunRef.current !== runId) return;
        setSpeaking(false);
        clearAudioPlayback();
        if (dialogueModeRef.current) {
          window.setTimeout(() => startListening(), 520);
        }
      };
      audio.onerror = () => {
        if (speechRunRef.current !== runId) return;
        setSpeaking(false);
        setVoiceError("Ses üretilemedi.");
        clearAudioPlayback();
      };

      setVoiceLoading(false);
      setSpeaking(true);
      await audio.play();
      return true;
    } catch {
      if (speechRunRef.current !== runId) return false;
      setVoiceLoading(false);
      setSpeaking(false);
      clearAudioPlayback();
      const fallbackSpoke = speakWithBrowserFallback(cleanText);
      setVoiceError(
        fallbackSpoke
          ? "Kaliteli ses üretilemedi; tarayıcı sesi kullanılıyor."
          : "Ses üretilemedi.",
      );
      return fallbackSpoke;
    }
  };

  const send = (message: string) => {
    const text = message.trim();
    if (!text || chat.isPending) return;
    setLastUserText(text);
    setMessages((items) => [...items, { role: "user", text }]);
    setInput("");
    chat.mutate(text, {
      onSuccess: (response) => {
        setMessages((items) => [
          ...items,
          { role: "agent", text: response.answer, meta: response },
        ]);
        void speak(response.answer).then((spoke) => {
          if (!spoke && dialogueModeRef.current) {
            window.setTimeout(() => startListening(), 520);
          }
        });
      },
      onError: () => {
        const fallback =
          "API chat yaniti alinamadi. Katman 0 sadece mevcut backend verisine bagli calisir; baglanti gelince soruyu yeniden cevaplayabilirim.";
        setMessages((items) => [...items, { role: "agent", text: fallback }]);
        void speak(fallback).then((spoke) => {
          if (!spoke && dialogueModeRef.current) {
            window.setTimeout(() => startListening(), 520);
          }
        });
      },
    });
  };

  const startListening = () => {
    if (listeningRef.current || chatPendingRef.current) return;
    const Recognition = getSpeechRecognition();
    if (!Recognition) return;
    const recognition = new Recognition();
    recognition.lang = "tr-TR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript ?? "";
      setListening(false);
      if (transcript.trim()) send(transcript);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
    }
  };

  const stopSpeaking = () => {
    setDialogueMode(false);
    speechRunRef.current += 1;
    clearAudioPlayback();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    recognitionRef.current?.stop();
    setListening(false);
    setSpeaking(false);
    setVoiceLoading(false);
  };

  const toggleDialogueMode = () => {
    const next = !dialogueMode;
    setDialogueMode(next);
    if (next) {
      setVoiceEnabled(true);
      window.setTimeout(() => startListening(), 120);
    } else {
      stopSpeaking();
    }
  };

  const modelMode = listening
    ? "listening"
    : chat.isPending
      ? "thinking"
      : voiceLoading
        ? "thinking"
        : speaking
          ? "speaking"
          : "idle";
  const positions = paper.data?.open_positions ?? [];
  const totalPnl = paper.data?.unrealized_pnl_usd ?? 0;
  const subtitleSpeaker =
    modelMode === "listening"
      ? "SEN"
      : modelMode === "thinking"
        ? "ANALIZ"
        : modelMode === "speaking"
          ? "E-yAy"
          : dialogueMode
            ? "CANLI DIYALOG"
            : "E-yAy";
  const subtitleText =
    modelMode === "listening"
      ? "Dinliyorum. Sorunu bitirince otomatik olarak sisteme iletecegim."
      : modelMode === "thinking"
        ? lastUserText
          ? `Sorun okunuyor: ${shortLine(lastUserText, 110)}`
          : "Sistem state, haber, risk ve sinyal katmanlarini tararken bekle."
        : modelMode === "speaking"
          ? shortLine(latestAgentText, 132)
        : dialogueMode
          ? "Karsilikli mod acik. Konusma bitince tekrar dinlemeye donecegim."
          : shortLine(latestAgentText, 132);
  const activeQuestionText = activeExchange.user?.text ?? lastUserText;
  const activeEvidence = activeExchange.agent?.meta?.evidence_used?.slice(0, 4) ?? [];
  const historyMessages = messages
    .filter((_, index) => index !== activeExchange.agentIndex && index !== activeExchange.userIndex)
    .slice(-4);

  useEffect(() => {
    const text = latestAgentText.trim();
    if (!text) {
      setStreamedText("");
      return;
    }

    let index = 0;
    let cancelled = false;
    const stride = modelMode === "speaking" ? 3 : modelMode === "thinking" ? 2 : 5;
    const delay = modelMode === "speaking" ? 20 : modelMode === "thinking" ? 28 : 12;
    setStreamedText("");

    const tick = () => {
      if (cancelled) return;
      index = Math.min(text.length, index + stride);
      setStreamedText(text.slice(0, index));
      if (index < text.length) {
        window.setTimeout(tick, delay);
      }
    };

    const id = window.setTimeout(tick, 80);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [latestAgentText, modelMode]);

  return (
    <section className="grid min-h-full gap-4 xl:h-full xl:min-h-0 xl:grid-cols-[minmax(360px,1fr)_minmax(380px,1fr)_minmax(360px,1fr)]">
      {/* ── Sutun 1: Acik pozisyon yonetim merkezi ───────────────── */}
      <div className="order-3 flex h-[calc(100dvh-8rem)] min-h-0 snap-start flex-col xl:order-1 xl:h-full xl:min-h-0">
        <Layer0PositionManager
          positions={positions}
          totalPnl={totalPnl}
          loading={paper.isLoading}
        />
      </div>

      {/* ── Sutun 2: Human-computer model + karar hero ──────────────── */}
      <div className="layer0-center-stack order-1 flex h-[calc(100dvh-8rem)] min-h-0 snap-start flex-col gap-3 xl:order-2 xl:h-full xl:min-h-0">
        <div className="reporter-model-card shrink-0">
          <Layer0HumanComputerModel
            mode={modelMode}
            dataQuality={dataQualityPulse}
            onOpenLayer1={() => onNavigate(1)}
          />
          <div className="reporter-model-hud">
            <div className="reporter-model-spectrum" aria-hidden>
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>

        <Layer0StatusCore hero={hero} onNavigate={onNavigate} />
      </div>

      {/* ── Sutun 3: Konusma paneli ─────────────────────────────────── */}
      <div className={`reporter-agent-console layer0-voice-console layer0-voice-console--${modelMode} order-2 h-[calc(100dvh-8rem)] min-h-0 snap-start xl:order-3 xl:h-full xl:min-h-0`}>
        <div className="reporter-agent-grid" />
        <div className="reporter-agent-orb" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div className="layer0-voice-beam" aria-hidden />

        <div className="relative z-10 flex items-center justify-between gap-2 border-b border-white/[0.08] pb-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-white/85">
            <span className="grid h-6 w-6 place-items-center rounded-md border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan">
              ▢
            </span>
            <span className="min-w-0">
              <span className="block text-[9px] font-medium tracking-[0.26em] text-accent-cyan/70">
                CEVAP KANALI
              </span>
              <span className="block truncate text-base normal-case tracking-normal text-white/90">
                KONUŞMA PANELİ
              </span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={toggleDialogueMode}
              title="Karsilikli konusma modu"
              className={`grid h-7 w-7 place-items-center rounded-lg border text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40 ${
                dialogueMode
                  ? "border-accent-cyan/50 bg-accent-cyan/12 text-accent-cyan"
                  : "border-white/10 bg-white/[0.035] text-white/45"
              }`}
            >
              IO
            </button>
            <button
              type="button"
              onClick={() => setVoiceEnabled((value) => !value)}
              title="Sesli cevap"
              className={`grid h-7 w-7 place-items-center rounded-lg border text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40 ${
                voiceEnabled
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                  : "border-white/10 bg-white/[0.035] text-white/45"
              }`}
            >
              VO
            </button>
            <button
              type="button"
              onClick={startListening}
              disabled={!micReady || listening || chat.isPending}
              title="Mikrofon"
              className={`grid h-7 w-7 place-items-center rounded-lg border text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40 ${
                listening
                  ? "border-red-400/45 bg-red-400/10 text-red-300"
                  : "border-accent-cyan/35 bg-accent-cyan/8 text-accent-cyan"
              }`}
            >
              {listening ? "..." : "MI"}
            </button>
            <button
              type="button"
              onClick={stopSpeaking}
              title="Sesi durdur"
              className="grid h-7 w-7 place-items-center rounded-lg border border-white/10 bg-white/[0.035] text-[10px] uppercase tracking-widest text-white/55 transition-colors hover:border-white/20 hover:text-white"
            >
              ST
            </button>
          </div>
        </div>

        <div className="relative z-10 mt-3 flex items-center justify-between gap-3 text-[10px] uppercase tracking-widest text-white/38">
          <span>CANLI ANALIZ</span>
          <span className="text-accent-cyan/60">
            {voiceLoading ? "AUDIO RENDER" : speaking ? "VOICE OUT" : listening ? "MIC IN" : subtitleSpeaker}
          </span>
        </div>

        <div className="layer0-voice-scroll mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          <div className="layer0-voice-transcript">
            <div className="layer0-voice-transcript-glow" aria-hidden />
            <div className="layer0-voice-kicker">{subtitleText}</div>
            {activeQuestionText ? (
              <div className="layer0-voice-question-chip">
                <span>Sen</span>
                <p>{activeQuestionText}</p>
              </div>
            ) : null}
            <p className="layer0-voice-stream-text">
              {streamedText}
              <span className="layer0-voice-caret" aria-hidden />
            </p>
            {activeEvidence.length ? (
              <div className="layer0-voice-evidence">
                <span className="layer0-voice-evidence__label">kanit</span>
                {activeEvidence.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => {
                if (speaking || voiceLoading) {
                  stopSpeaking();
                } else {
                  void speak(latestAgentText);
                }
              }}
              disabled={!voiceEnabled}
              className="layer0-voice-read-button"
            >
              {voiceLoading ? "SES URETILIYOR" : speaking ? "DURDUR" : "SESLI OKU"}
            </button>
            {voiceError ? <div className="layer0-voice-error">{voiceError}</div> : null}
          </div>
          {historyMessages.length ? (
            <>
              <div className="layer0-voice-history-label">Onceki konusmalar</div>
              {historyMessages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`layer0-voice-log-row ${
                  message.role === "user"
                    ? "layer0-voice-log-row--user"
                    : message.meta?.refused
                      ? "layer0-voice-log-row--blocked"
                      : "layer0-voice-log-row--agent"
                }`}
              >
                <div className="layer0-voice-log-role">
                  {message.role === "user" ? "Sen" : "E-yAy"}
                </div>
                <div className="layer0-voice-log-text">{message.text}</div>
                {message.role === "agent" && message.meta?.evidence_used?.length ? (
                  <div className="layer0-voice-log-evidence">
                    kanit: {message.meta.evidence_used.slice(0, 3).join(" / ")}
                  </div>
                ) : null}
              </div>
              ))}
            </>
          ) : null}
          {chat.isPending ? (
            <div className="rounded-2xl border border-accent-cyan/20 bg-accent-cyan/8 px-3 py-2 text-xs uppercase tracking-widest text-accent-cyan/76">
              Sistem state okunuyor...
            </div>
          ) : null}
        </div>

        <div className="layer0-voice-prompts">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => send(prompt)}
              disabled={chat.isPending}
            >
              {prompt}
            </button>
          ))}
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(input);
          }}
          className="layer0-voice-input"
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ornek: 15 dakikalik firsat var mi?"
            maxLength={2000}
          />
          <button
            type="submit"
            disabled={chat.isPending || !input.trim()}
          >
            Sor
          </button>
        </form>
      </div>
    </section>
  );
}
