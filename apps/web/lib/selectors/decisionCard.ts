// Karar kartı (karar-destek adım 2): onay bekleyen adayın biletinden owner'ın araçları.
// Veri biletin `technical_detail.owner_card` bölümünden gelir (sözleşmede serbest alan; backend
// `packages/paper/decision_card.py`). Burada hesap yok, yalnız okunur metne çevirme.

import { fmtNum } from "@/lib/format";
import type { ManualReadyTrade, TradeTicket } from "@/types/generated/api";

export type CardTone = "good" | "bad" | "neutral" | "muted";
export type CardLine = { label: string; text: string; tone: CardTone };
export type CardPlan = { entry: number; stop: number; target: number; rr: number; riskPct: number };
export type DecisionCardView = { plan: CardPlan | null; lines: CardLine[] };

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const ok = (v: unknown): v is Obj => isObj(v) && v.status === "ok";

function price(v: unknown): string {
  const n = num(v);
  return n == null ? "—" : fmtNum(n, n >= 100 ? 2 : 4);
}

function dec(v: number, digits = 2): string {
  return v.toFixed(digits).replace(".", ",");
}

const DIR_TR: Record<string, string> = { up: "yukarı", down: "aşağı", range: "yatay" };

/** Adayın biletini bul: önce aynı sinyal kimliği, yoksa aynı sembol × TF × yön. */
export function findTicket(item: ManualReadyTrade, tickets: TradeTicket[] | undefined): TradeTicket | undefined {
  if (!tickets?.length) return undefined;
  return (
    (item.signal_id ? tickets.find((t) => t.signal_id === item.signal_id) : undefined) ??
    tickets.find((t) => t.symbol === item.symbol && t.timeframe === item.timeframe && t.side === item.side)
  );
}

function planOf(ticket: TradeTicket): CardPlan | null {
  const s = ticket.summary;
  const entry = num(s?.entry_price);
  const stop = num(s?.stop_loss);
  const target = num(s?.take_profit);
  const rr = num(s?.rr_ratio);
  if (entry == null || stop == null || target == null || rr == null) return null;
  return { entry, stop, target, rr, riskPct: num(s?.risk_pct_equity) ?? 0 };
}

function structureLine(v: unknown): CardLine {
  const label = "Üst TF yapısı";
  if (!ok(v)) return { label, text: "veri yok", tone: "muted" };
  const dir = str(v.direction) ?? "";
  const tone: CardTone = v.aligned === true ? "good" : dir === "range" ? "neutral" : "bad";
  const note = v.aligned === true ? " · adayla aynı yön" : dir === "range" ? "" : " · adaya ters";
  return { label, text: `${str(v.timeframe) ?? ""} ${DIR_TR[dir] ?? dir}${note}`, tone };
}

function fibLine(v: unknown): CardLine {
  if (!ok(v)) return { label: "Fib", text: "veri yok", tone: "muted" };
  const label = `Fib (${str(v.frame) ?? ""})`;
  const r = num(v.retracement);
  const ext = Array.isArray(v.extensions)
    ? v.extensions
        .filter(isObj)
        .map((e) => `${dec(num(e.ratio) ?? 0, 3)}: ${price(e.price)}`)
        .join(" · ")
    : "";
  if (r == null) return { label, text: `belirgin trend yok${ext ? ` · uzantı ${ext}` : ""}`, tone: "neutral" };
  const zone = v.in_golden_zone === true;
  const text = `geri çekilme %${Math.round(r * 100)}${zone ? " · 0,382–0,618 bölgesinde" : ""}${ext ? ` · uzantı ${ext}` : ""}`;
  return { label, text, tone: zone ? "good" : "neutral" };
}

function swingLine(v: unknown): CardLine {
  const label = "Önceki dip / tepe";
  if (!ok(v)) return { label, text: "veri yok", tone: "muted" };
  const atr = (x: unknown) => {
    const n = num(x);
    return n == null ? "" : ` (${dec(n, 1)} ATR)`;
  };
  return { label, text: `dip ${price(v.prev_low)}${atr(v.prev_low_atr)} · tepe ${price(v.prev_high)}${atr(v.prev_high_atr)}`, tone: "neutral" };
}

function zeroTwoLine(v: unknown): CardLine {
  const label = "0-2 çizgisi";
  if (!ok(v)) return { label, text: "veri yok", tone: "muted" };
  if (v.found !== true) return { label, text: "kurulum yok", tone: "neutral" };
  const valid = v.validity === "GECERLI";
  const broken = v.last_touch === "CLOSE_BREAK";
  const parts = [
    `${DIR_TR[str(v.direction) ?? ""] ?? str(v.direction)} 0-2`,
    valid ? "geçerli" : "iptal (dalga mumu çizgiye değdi)",
    `çizgi ${price(v.line_price)}`,
  ];
  if (broken) parts.push("kapanışla kırıldı");
  else if (v.last_touch === "WICK_TOUCH") parts.push("fitil değdi");
  if (v.aligned !== true) parts.push("adaya ters");
  const tone: CardTone = v.aligned !== true ? "bad" : valid && !broken && v.price_on_trend_side === true ? "good" : "neutral";
  return { label, text: parts.join(" · "), tone };
}

function eventsLine(v: unknown): CardLine {
  const label = "Olaylar";
  if (!ok(v)) return { label, text: "takvim yok", tone: "muted" };
  const items = Array.isArray(v.items) ? v.items.filter(isObj) : [];
  if (!items.length) {
    const h = num(v.hold_hours);
    return { label, text: `pozisyon süresinde${h != null ? ` (${Math.round(h)} sa)` : ""} önemli olay yok`, tone: "neutral" };
  }
  const text = items
    .map((e) => `${str(e.title) ?? "olay"} · ${dec(num(e.hours_until) ?? 0, 1)} sa sonra${e.importance === "critical" ? " (kritik)" : ""}`)
    .join(" · ");
  return { label, text, tone: "bad" };
}

function historyLine(v: unknown): CardLine {
  const label = "Geçmiş (60 gün)";
  if (!ok(v)) return { label, text: "defter yok", tone: "muted" };
  const n = num(v.n) ?? 0;
  if (!n) return { label, text: "bu sembol / TF / yönde aday yok", tone: "muted" };
  const mean = num(v.mean_net_r) ?? 0;
  const win = num(v.win_rate) ?? 0;
  const small = n < 30;
  const text = `${n} aday-bar · ort. ${mean > 0 ? "+" : ""}${dec(mean)}R (maliyet dahil) · isabet %${Math.round(win * 100)}${small ? " · örnek az, güvenme" : ""}`;
  return { label, text, tone: small ? "muted" : mean > 0 ? "good" : "bad" };
}

export function selectDecisionCard(ticket: TradeTicket | undefined): DecisionCardView | null {
  if (!ticket) return null;
  const card = isObj(ticket.technical_detail) ? ticket.technical_detail.owner_card : undefined;
  const plan = planOf(ticket);
  if (!isObj(card)) return { plan, lines: [] };
  return {
    plan,
    lines: [
      structureLine(card.structure),
      fibLine(card.fib),
      swingLine(card.swing),
      zeroTwoLine(card.zero_two),
      eventsLine(card.events),
      historyLine(card.history),
    ],
  };
}
