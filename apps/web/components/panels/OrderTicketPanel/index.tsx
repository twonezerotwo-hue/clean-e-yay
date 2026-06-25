"use client";

import { useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { MobileFlipCard } from "@/components/cockpit/MobileFlipCard";
import {
  useCancelOrder,
  usePendingOrders,
  usePlaceOrder,
} from "@/lib/queries/hooks";
import type { OrderResult } from "@/lib/api/client";

const SYMBOLS = [
  { sym: "BTCUSD", label: "BTC" },
  { sym: "ETHUSD", label: "ETH" },
  { sym: "XAUUSD", label: "Altın" },
  { sym: "XAGUSD", label: "Gümüş" },
];

const TYPES = [
  { key: "market", label: "Market" },
  { key: "limit", label: "Limit" },
  { key: "stop", label: "Stop" },
  { key: "stop_limit", label: "Stop-Limit" },
];

export function OrderTicketPanel() {
  const place = usePlaceOrder();
  const pending = usePendingOrders();
  const cancel = useCancelOrder();

  const [symbol, setSymbol] = useState("BTCUSD");
  const [side, setSide] = useState<"long" | "short">("long");
  const [size, setSize] = useState("");
  const [type, setType] = useState("market");
  const [price, setPrice] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [result, setResult] = useState<OrderResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const needsPrice = type !== "market";
  const needsLimit = type === "stop_limit";

  const submit = () => {
    setError(null);
    setResult(null);
    const sizeNum = Number(size);
    if (!sizeNum || sizeNum <= 0) {
      setError("Tutar gir (dolar).");
      return;
    }
    const body: Record<string, unknown> = {
      symbol,
      side,
      size_usd: sizeNum,
      order_type: type,
    };
    if (needsPrice) {
      const p = Number(price);
      if (!p || p <= 0) {
        setError("Tetik fiyatı gir.");
        return;
      }
      body.entry_price = p;
    }
    if (needsLimit) {
      const lp = Number(limitPrice);
      if (!lp || lp <= 0) {
        setError("Limit fiyatı gir.");
        return;
      }
      body.limit_price = lp;
    }
    place.mutate(body as never, {
      onSuccess: (r) => {
        setResult(r);
        setSize("");
        setPrice("");
        setLimitPrice("");
      },
      onError: (e) => setError(e instanceof Error ? e.message.slice(0, 120) : "Emir başarısız"),
    });
  };

  const orders = pending.data?.orders ?? [];

  return (
    <>
    <div className="hidden h-full min-[769px]:block">
    <PanelFrame id="order_ticket" className="h-full border-accent-cyan/25">
      <PanelHeader
        title="Order Ticket"
        subtitle="market / limit / stop / stop-limit — kâğıt üzerinde, gerçek emir yok"
      />

      <div className="space-y-3">
        {/* Sembol */}
        <div className="flex flex-wrap gap-1.5">
          {SYMBOLS.map((s) => (
            <button
              key={s.sym}
              type="button"
              onClick={() => setSymbol(s.sym)}
              className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                symbol === s.sym
                  ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                  : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white/80"
              }`}
            >
              {s.label}
            </button>
          ))}
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-24 rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs uppercase text-white/80 outline-none focus:border-accent-cyan/45"
          />
        </div>

        {/* Yön */}
        <div className="grid grid-cols-2 gap-2">
          {(["long", "short"] as const).map((sd) => (
            <button
              key={sd}
              type="button"
              onClick={() => setSide(sd)}
              className={`rounded-lg border py-2 text-sm font-semibold uppercase tracking-widest transition-colors ${
                side === sd
                  ? sd === "long"
                    ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300"
                    : "border-red-400/50 bg-red-400/15 text-red-300"
                  : "border-white/10 bg-white/[0.03] text-white/45"
              }`}
            >
              {sd === "long" ? "AL" : "SAT"}
            </button>
          ))}
        </div>

        {/* Tip */}
        <div className="grid grid-cols-4 gap-1.5">
          {TYPES.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setType(t.key)}
              className={`rounded-lg border py-1.5 text-[11px] transition-colors ${
                type === t.key
                  ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                  : "border-white/10 bg-white/[0.03] text-white/50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tutar + fiyatlar */}
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="text-[10px] uppercase tracking-widest text-white/40">
            Tutar ($)
            <input
              value={size}
              onChange={(e) => setSize(e.target.value)}
              inputMode="decimal"
              placeholder="10000"
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
            />
          </label>
          {needsPrice ? (
            <label className="text-[10px] uppercase tracking-widest text-white/40">
              {type === "stop_limit" ? "Stop tetik" : "Tetik fiyatı"}
              <input
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                inputMode="decimal"
                placeholder="56.00"
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
              />
            </label>
          ) : null}
          {needsLimit ? (
            <label className="text-[10px] uppercase tracking-widest text-white/40">
              Limit fiyatı
              <input
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                inputMode="decimal"
                placeholder="56.50"
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
              />
            </label>
          ) : null}
        </div>

        <button
          type="button"
          onClick={submit}
          disabled={place.isPending}
          className="w-full rounded-xl border border-accent-cyan/40 bg-accent-cyan/12 py-2.5 text-sm font-semibold uppercase tracking-widest text-accent-cyan transition-colors hover:bg-accent-cyan/20 disabled:opacity-40"
        >
          {place.isPending ? "Gönderiliyor…" : "Emri Gönder"}
        </button>

        {error ? (
          <div className="rounded-lg border border-red-400/35 bg-red-400/10 px-3 py-2 text-xs text-red-200">
            {error}
          </div>
        ) : null}
        {result ? (
          <div className="rounded-lg border border-emerald-400/35 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">
            {result.kind === "market"
              ? `Açıldı: ${result.symbol} ${result.side === "long" ? "AL" : "SAT"} $${Math.round(
                  result.size_usd,
                )} @ ${result.entry_price?.toFixed(2)}`
              : `Bekleyen ${result.kind} emri: ${result.symbol} ${
                  result.side === "long" ? "AL" : "SAT"
                } $${Math.round(result.size_usd)}, tetik ${result.trigger_price?.toFixed(2)}`}
          </div>
        ) : null}

        {/* Bekleyen emirler */}
        <div className="rounded-lg border border-white/10 bg-black/24 p-3">
          <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-white/40">
            <span>Bekleyen emirler ({orders.length})</span>
          </div>
          {orders.length ? (
            <div className="space-y-1.5">
              {orders.map((o) => (
                <div
                  key={o.id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-2.5 py-1.5 text-xs"
                >
                  <span className="text-white/80">
                    <span
                      className={`mr-1.5 rounded px-1 py-0.5 text-[10px] font-semibold uppercase ${
                        o.side === "long"
                          ? "bg-emerald-400/15 text-emerald-300"
                          : "bg-red-400/15 text-red-300"
                      }`}
                    >
                      {o.side === "long" ? "AL" : "SAT"}
                    </span>
                    {o.symbol} · {o.order_type} · {o.trigger_price.toFixed(2)} · $
                    {Math.round(o.size_usd)}
                  </span>
                  <button
                    type="button"
                    onClick={() => cancel.mutate(o.id)}
                    className="rounded-md border border-white/12 px-2 py-0.5 text-[10px] uppercase tracking-widest text-white/50 transition-colors hover:border-red-400/40 hover:text-red-200"
                  >
                    İptal
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs italic text-white/40">Bekleyen emrin yok.</div>
          )}
        </div>
      </div>
    </PanelFrame>
    </div>
    <MobileFlipCard
      className="min-[769px]:hidden"
      title="Order Ticket"
      front={
        <div className="mobile-order-front">
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Order Ticket</p>
              <strong>{symbol}</strong>
            </div>
            <span>{orders.length ? `${orders.length} bekleyen` : "ticket yok"}</span>
          </div>
          <div className="mobile-metric-grid">
            <div>
              <span>Yön</span>
              <strong>{side === "long" ? "AL" : "SAT"}</strong>
            </div>
            <div>
              <span>Tip</span>
              <strong>{type}</strong>
            </div>
            <div>
              <span>Tutar</span>
              <strong>{size ? `$${size}` : "---"}</strong>
            </div>
            <div>
              <span>Tetik</span>
              <strong>{needsPrice ? price || "---" : "market"}</strong>
            </div>
          </div>
          <p className="mobile-summary-line">
            PAPER_SAFE / NO_EXECUTION korunur; gerçek broker emri yok.
          </p>
          <p className="mobile-flip-hint">Detay için dokun</p>
        </div>
      }
      back={
        <div className="mobile-flip-card__scroll mobile-order-back" data-no-flip>
          <div className="mobile-back-head">
            <div>
              <p className="mobile-kicker">Emir formu</p>
              <strong>{symbol}</strong>
            </div>
            <span>{type}</span>
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {SYMBOLS.map((s) => (
                <button
                  key={s.sym}
                  type="button"
                  onClick={() => setSymbol(s.sym)}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    symbol === s.sym
                      ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                      : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white/80"
                  }`}
                >
                  {s.label}
                </button>
              ))}
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="w-24 rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs uppercase text-white/80 outline-none focus:border-accent-cyan/45"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              {(["long", "short"] as const).map((sd) => (
                <button
                  key={sd}
                  type="button"
                  onClick={() => setSide(sd)}
                  className={`rounded-lg border py-2 text-sm font-semibold uppercase tracking-widest transition-colors ${
                    side === sd
                      ? sd === "long"
                        ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300"
                        : "border-red-400/50 bg-red-400/15 text-red-300"
                      : "border-white/10 bg-white/[0.03] text-white/45"
                  }`}
                >
                  {sd === "long" ? "AL" : "SAT"}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              {TYPES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setType(t.key)}
                  className={`rounded-lg border py-1.5 text-[11px] transition-colors ${
                    type === t.key
                      ? "border-accent-cyan/45 bg-accent-cyan/12 text-accent-cyan"
                      : "border-white/10 bg-white/[0.03] text-white/50"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="grid gap-2">
              <label className="text-[10px] uppercase tracking-widest text-white/40">
                Tutar ($)
                <input
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  inputMode="decimal"
                  placeholder="10000"
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
                />
              </label>
              {needsPrice ? (
                <label className="text-[10px] uppercase tracking-widest text-white/40">
                  {type === "stop_limit" ? "Stop tetik" : "Tetik fiyatı"}
                  <input
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    inputMode="decimal"
                    placeholder="56.00"
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
                  />
                </label>
              ) : null}
              {needsLimit ? (
                <label className="text-[10px] uppercase tracking-widest text-white/40">
                  Limit fiyatı
                  <input
                    value={limitPrice}
                    onChange={(e) => setLimitPrice(e.target.value)}
                    inputMode="decimal"
                    placeholder="56.50"
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-sm text-white/85 outline-none focus:border-accent-cyan/45"
                  />
                </label>
              ) : null}
            </div>

            <button
              type="button"
              onClick={submit}
              disabled={place.isPending}
              className="w-full rounded-xl border border-accent-cyan/40 bg-accent-cyan/12 py-2.5 text-sm font-semibold uppercase tracking-widest text-accent-cyan transition-colors hover:bg-accent-cyan/20 disabled:opacity-40"
            >
              {place.isPending ? "Gönderiliyor..." : "Emri Gönder"}
            </button>

            {error ? (
              <div className="rounded-lg border border-red-400/35 bg-red-400/10 px-3 py-2 text-xs text-red-200">
                {error}
              </div>
            ) : null}
            {result ? (
              <div className="rounded-lg border border-emerald-400/35 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">
                {result.kind === "market"
                  ? `Açıldı: ${result.symbol} ${result.side === "long" ? "AL" : "SAT"} $${Math.round(
                      result.size_usd,
                    )} @ ${result.entry_price?.toFixed(2)}`
                  : `Bekleyen ${result.kind} emri: ${result.symbol} ${
                      result.side === "long" ? "AL" : "SAT"
                    } $${Math.round(result.size_usd)}, tetik ${result.trigger_price?.toFixed(2)}`}
              </div>
            ) : null}

            <div className="rounded-lg border border-white/10 bg-black/24 p-3">
              <div className="mb-2 text-[10px] uppercase tracking-widest text-white/40">
                Bekleyen emirler ({orders.length})
              </div>
              {orders.length ? (
                <div className="space-y-1.5">
                  {orders.map((o) => (
                    <div
                      key={o.id}
                      className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-2.5 py-1.5 text-xs"
                    >
                      <span className="text-white/80">
                        {o.symbol} · {o.order_type} · {o.trigger_price.toFixed(2)} · ${Math.round(o.size_usd)}
                      </span>
                      <button
                        type="button"
                        onClick={() => cancel.mutate(o.id)}
                        className="rounded-md border border-white/12 px-2 py-0.5 text-[10px] uppercase tracking-widest text-white/50 transition-colors hover:border-red-400/40 hover:text-red-200"
                      >
                        İptal
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs italic text-white/40">Bekleyen emrin yok.</div>
              )}
            </div>
          </div>
        </div>
      }
    />
    </>
  );
}
