"use client";

import { useEffect, useMemo, useState } from "react";

import { fmtNum } from "@/lib/format";
import { useManualReady, useManualReadyAction } from "@/lib/queries/hooks";
import type { ManualReadyActionResult, ManualReadyTrade } from "@/types/generated/api";

// Onay kuyruğu (karar-destek adım 1, 2026-11-16): tick'in owner onayına bıraktığı adaylar.
// Kuyruk boşken HİÇ çizilmez — açık pozisyon sütununun mevcut görünümü değişmez.
// Aday kendi zaman diliminin BİR barı yaşar; eskimişi sunucu zaten göstermez, buradaki kalan
// süre yalnız gösterim içindir. Onay sunucuda RiskGate + güncel fiyat + fiyat kaçma (0,5 ATR)
// denetiminden geçer; düğme hiçbirini atlayamaz. Gerçek emir YOK (PAPER_SAFE).

const TF_SECONDS: Record<string, number> = { "15m": 900, "1h": 3600, "4h": 14_400, "1d": 86_400, "1w": 604_800 };
const RESULT_MS = 10_000;

type Action = "approve" | "reject" | "dismiss";
type Outcome = { symbol: string; text: string; tone: "ok" | "warn" | "info" };

const OUTCOME_TONE: Record<Outcome["tone"], string> = {
  ok: "text-emerald-200",
  warn: "text-amber-200",
  info: "text-white/65",
};

function remainingSec(item: ManualReadyTrade, nowMs: number): number {
  const start = Date.parse(item.requested_at);
  if (!Number.isFinite(start)) return 0;
  const ttl = (TF_SECONDS[item.timeframe] ?? 3600) * 1000;
  return Math.max(0, Math.round((start + ttl - nowMs) / 1000));
}

function fmtRemaining(sec: number): string {
  if (sec >= 3600) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return m ? `${h} sa ${m} dk` : `${h} sa`;
  }
  return `${Math.max(1, Math.ceil(sec / 60))} dk`;
}

function fmtPrice(v?: number): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return fmtNum(v, v >= 100 ? 2 : 4);
}

function reasonText(reason?: string): string {
  const r = (reason ?? "").trim();
  if (!r) return "Neden belirtilmedi";
  if (r.startsWith("market_session_no_relevant_market")) return "İlgili piyasa seansı kapalı";
  if (r.startsWith("market_session_opening_window")) return "Seans açılış penceresi";
  if (r.startsWith("market_session_calendar_unknown")) return "Seans takvimi bilinmiyor";
  if (r.startsWith("market_session")) return "Seans kapısı onay istiyor";
  if (r.startsWith("shadow_activation")) return "Yeni karar hattının önerisi";
  if (r.startsWith("regime_")) return "Fırtına rejimi — onay gerekli";
  if (r.includes("conflict")) return "Modüller çelişiyor — onay gerekli";
  return r;
}

function blockedText(reason?: string): string {
  const r = reason ?? "";
  if (r === "expired") return "Süresi doldu — açılmadı";
  const moved = /^price_moved:([\d.]+)atr$/.exec(r);
  if (moved) return `Fiyat kaçtı (${moved[1].replace(".", ",")} ATR) — açılmadı`;
  if (r.startsWith("risk_gate:")) return `Risk kapısı (${r.slice(10)}) — açılmadı`;
  if (r === "price_insane") return "Fiyat denetimi geçmedi — açılmadı";
  return r ? `Engellendi: ${r}` : "Engellendi";
}

function outcomeOf(item: ManualReadyTrade, action: Action, res: ManualReadyActionResult): Outcome {
  const symbol = item.symbol;
  switch (res.status) {
    case "opened":
      return { symbol, tone: "ok", text: `Paper pozisyon açıldı · ${fmtPrice(res.price)}` };
    case "rejected":
      return { symbol, tone: "info", text: "Reddedildi — aynı sinyal sürdükçe tekrar gelmez" };
    case "dismissed":
      return { symbol, tone: "info", text: "Geçildi — sinyal sürerse yeniden gelir" };
    case "no_price":
      return { symbol, tone: "warn", text: "Güncel fiyat yok — açılmadı" };
    case "not_found":
      return { symbol, tone: "warn", text: "Aday artık kuyrukta değil" };
    case "blocked":
      return { symbol, tone: "warn", text: blockedText(res.reason) };
    default:
      return { symbol, tone: "info", text: action === "approve" ? res.status : `${action}: ${res.status}` };
  }
}

export function Layer0ApprovalQueue() {
  const queue = useManualReady();
  const act = useManualReadyAction();
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  // Yalnız kalan süre göstergesi için görsel saat (veri çekmez).
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!outcome) return;
    const timer = setTimeout(() => setOutcome(null), RESULT_MS);
    return () => clearTimeout(timer);
  }, [outcome]);

  const items = useMemo(
    () =>
      [...(queue.data?.manual_ready ?? [])]
        .filter((m) => remainingSec(m, nowMs) > 0)
        .sort((a, b) => Date.parse(b.requested_at) - Date.parse(a.requested_at)),
    [queue.data, nowMs],
  );

  if (!items.length && !outcome) return null;

  const run = async (item: ManualReadyTrade, action: Action) => {
    setBusyId(item.id);
    try {
      const res = await act.mutateAsync({ manualId: item.id, action });
      setOutcome(outcomeOf(item, action, res));
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setOutcome({
        symbol: item.symbol,
        tone: "warn",
        text: message === "not_found" ? "Aday artık kuyrukta değil" : message || "İşlem tamamlanamadı",
      });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section
      aria-label="Onay bekleyen adaylar"
      data-testid="approval-queue"
      className="layer0-card relative mb-3 flex max-h-[45%] shrink-0 flex-col overflow-hidden !border-amber-300/25 !p-3 shadow-[0_0_36px_rgba(251,191,36,0.06),inset_0_1px_0_rgba(255,255,255,0.05)]"
    >
      <div className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/45 to-transparent" />
      <div className="flex items-center justify-between gap-3 border-b border-amber-300/10 pb-2">
        <div className="text-[13px] font-semibold uppercase tracking-[0.18em] text-white/88">Onay Bekleyen</div>
        <span className="rounded-full border border-amber-300/35 bg-amber-300/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-amber-100">
          {items.length}
        </span>
      </div>

      <ul className="mt-2 min-h-0 space-y-1.5 overflow-y-auto pr-0.5 [scrollbar-width:thin]">
        {items.map((item) => {
          const long = item.side === "long";
          const busy = busyId !== null;
          return (
            <li key={item.id} className="rounded-xl border border-white/[0.08] bg-black/20 px-2.5 py-2" data-testid="approval-item">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-mono text-[14px] font-black tracking-wide text-white">{item.symbol}</span>
                <span
                  className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] ${
                    long ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-200" : "border-red-400/35 bg-red-400/10 text-red-200"
                  }`}
                >
                  {long ? "LONG" : "SHORT"}
                </span>
                <span className="rounded-md border border-white/12 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-white/70">
                  {item.timeframe}
                </span>
                <span className="ml-auto font-mono text-[12px] font-semibold text-white/85" title="Kuyruğa girdiği fiyat">
                  {fmtPrice(item.requested_price)}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-[10px] leading-4">
                <span className="min-w-0 truncate text-white/55" title={item.reason ?? undefined}>
                  {reasonText(item.reason)}
                </span>
                <span className="shrink-0 font-mono text-amber-100/75" title="Bu süre dolunca aday düşer">
                  {fmtRemaining(remainingSec(item, nowMs))}
                </span>
              </div>
              <div className="mt-1.5 grid grid-cols-3 gap-1.5">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(item, "approve")}
                  aria-busy={busyId === item.id}
                  className="min-h-8 rounded-lg border border-accent-cyan/55 bg-accent-cyan/15 px-2 text-[10px] font-bold uppercase tracking-[0.11em] text-accent-cyan transition-colors hover:bg-accent-cyan/25 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Onayla
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(item, "reject")}
                  className="min-h-8 rounded-lg border border-red-400/40 bg-red-400/10 px-2 text-[10px] font-bold uppercase tracking-[0.11em] text-red-200 transition-colors hover:bg-red-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Reddet
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(item, "dismiss")}
                  className="min-h-8 rounded-lg border border-white/15 bg-white/[0.04] px-2 text-[10px] font-bold uppercase tracking-[0.11em] text-white/65 transition-colors hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Geç
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      <div aria-live="polite" className="min-h-0">
        {outcome ? (
          <p className={`mt-2 text-[10px] leading-4 ${OUTCOME_TONE[outcome.tone]}`} data-testid="approval-outcome">
            <span className="font-mono font-semibold">{outcome.symbol}</span> · {outcome.text}
          </p>
        ) : null}
      </div>
    </section>
  );
}
