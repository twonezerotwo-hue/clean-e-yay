"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useEventOutcomes, useRegimeReport } from "@/lib/queries/hooks";
import {
  EVENT_OUTCOME_STATUS_LABEL,
  selectNextEvent,
  selectOutcomeRows,
  selectRecentEventOutcomes,
} from "@/lib/selectors/event-outcomes";
import { selectCatalysts, selectEventRisk } from "@/lib/selectors/regime";
import type { Catalyst, EventOutcomeRecord, EventOutcomesView } from "@/types/generated/api";

const TONE: Record<string, { label: string; color: string; bg: string; text: string; weight: number }> = {
  critical: { label: "CRITICAL", color: "#f87171", bg: "rgba(248,113,113,0.18)", text: "text-red-300", weight: 4 },
  high: { label: "HIGH", color: "#fb923c", bg: "rgba(251,146,60,0.18)", text: "text-orange-300", weight: 3 },
  medium: { label: "MEDIUM", color: "#22d3ee", bg: "rgba(34,211,238,0.16)", text: "text-cyan-300", weight: 2 },
  low: { label: "LOW", color: "#94a3b8", bg: "rgba(148,163,184,0.14)", text: "text-slate-300", weight: 1 },
};

const GRID_DAYS = 20;
const GRID_COLS = 5;

function toneOf(importance?: string) {
  return TONE[(importance ?? "low").toLowerCase()] ?? TONE.low;
}

function eventDate(event: Catalyst) {
  const date = new Date(event.ts);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function ymd(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatDay(date: Date) {
  return {
    day: String(date.getDate()).padStart(2, "0"),
    month: date.toLocaleDateString("tr-TR", { month: "short" }).toUpperCase(),
    weekday: date.toLocaleDateString("tr-TR", { weekday: "short" }),
  };
}

function relativeLabel(event: Catalyst) {
  if (typeof event.hours_until === "number" && Math.abs(event.hours_until) < 48) {
    return event.hours_until >= 0 ? `+${Math.round(event.hours_until)}s` : `${Math.round(event.hours_until)}s`;
  }
  if (typeof event.days_until === "number") {
    return event.days_until >= 0 ? `+${event.days_until}g` : `${event.days_until}g`;
  }
  return formatDay(eventDate(event)).month;
}

function buildGrid(events: Catalyst[]) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  for (const event of events) {
    const date = eventDate(event);
    date.setHours(0, 0, 0, 0);
    if (date < start) start.setTime(date.getTime());
  }
  return Array.from({ length: GRID_DAYS }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
}

function narrative(event: Catalyst) {
  const title = event.title.toLowerCase();
  if (/fomc|fed|faiz|cpi|ppi|nfp|istihdam|enflasyon/.test(title)) {
    return [
      "DXY, US10Y, gold and Nasdaq first reaction should be watched.",
      "Policy surprise can tighten RiskGate without creating a trade.",
    ];
  }
  if (/oil|brent|iran|war|savas|attack|geo|opec/.test(title)) {
    return [
      "Energy and safe-haven demand can reprice quickly.",
      "Event premium is context only; execution remains blocked by gates.",
    ];
  }
  return [
    "Volatility can rise around the event window.",
    "This is a visual catalyst layer; no decision is produced.",
  ];
}

export function EventCalendarPanel() {
  const { data, isLoading } = useRegimeReport();
  const items = selectCatalysts(data, 12);
  const eventRisk = selectEventRisk(data);
  const [selected, setSelected] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused || items.length <= 1) return;
    const timer = window.setInterval(() => {
      setSelected((value) => (value + 1) % items.length);
    }, 5200);
    return () => window.clearInterval(timer);
  }, [items.length, paused]);

  const sorted = useMemo(
    () => items.slice().sort((a, b) => eventDate(a).getTime() - eventDate(b).getTime()),
    [items],
  );
  const active = sorted[Math.min(selected, sorted.length - 1)];
  const grid = useMemo(() => buildGrid(sorted), [sorted]);
  const byDate = useMemo(() => {
    const map = new Map<string, Catalyst[]>();
    for (const event of sorted) {
      const key = ymd(eventDate(event));
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [sorted]);

  return (
    <PanelFrame id="event_calendar" className="event-calendar-panel border-accent-cyan/20">
      <PanelHeader
        title="Olay Takvimi"
        subtitle="holographic event calendar / paper safe"
        actions={
          eventRisk?.restrictive ? (
            <span className="rounded border border-red-400/35 bg-red-400/10 px-2 py-1 text-[10px] uppercase tracking-widest text-red-300">
              {eventRisk.level}
            </span>
          ) : undefined
        }
      />
      <EventOutcomesStrip />
      {isLoading ? (
        <LoadingState />
      ) : !sorted.length || !active ? (
        <EmptyState />
      ) : (
        <div
          className="event-calendar-shell overflow-hidden rounded-lg border border-accent-cyan/16 bg-[#03101b]/92"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          <div className="event-calendar-main grid gap-0 lg:grid-cols-[340px_minmax(0,1fr)]">
            <ActiveEvent event={active} />
            <div className="event-calendar-grid-wrap relative border-t border-accent-cyan/14 p-3 lg:border-l lg:border-t-0">
              <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(34,211,238,0.7)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.7)_1px,transparent_1px)] [background-size:42px_42px]" />
              <div className="event-calendar-grid relative grid grid-cols-5 gap-1">
                {grid.map((date, index) => {
                  const events = byDate.get(ymd(date)) ?? [];
                  const topEvent = events
                    .slice()
                    .sort((a, b) => toneOf(b.importance).weight - toneOf(a.importance).weight)[0];
                  const tone = toneOf(topEvent?.importance);
                  const isActive = topEvent?.id === active.id;
                  const day = formatDay(date);
                  const style = {
                    "--event-color": tone.color,
                    background: isActive ? `linear-gradient(145deg, ${tone.bg}, rgba(2,8,18,0.84))` : undefined,
                    borderColor: isActive ? `${tone.color}99` : undefined,
                  } as CSSProperties;

                  return (
                    <button
                      key={index}
                      type="button"
                      disabled={!topEvent}
                      onClick={() => {
                        const next = sorted.findIndex((item) => item.id === topEvent?.id);
                        if (next >= 0) setSelected(next);
                      }}
                      className={`event-holo-cell relative aspect-square rounded-md border border-white/10 bg-white/[0.035] p-1 text-left transition ${
                        topEvent ? "hover:border-accent-cyan/45" : "opacity-50"
                      } ${isActive ? "event-holo-cell-active" : ""}`}
                      style={style}
                    >
                      <div className="text-[9px] uppercase tracking-widest text-white/32">{day.weekday}</div>
                      <div className={`mt-1 font-display text-lg leading-none ${isActive ? tone.text : "text-white/62"}`}>
                        {day.day}
                      </div>
                      {topEvent ? (
                        <span
                          className="absolute bottom-1 left-1 h-1.5 w-1.5 rounded-full"
                          style={{ background: tone.color, boxShadow: `0 0 10px ${tone.color}` }}
                        />
                      ) : null}
                      {events.length > 1 ? (
                        <span className="absolute right-1 top-1 text-[9px] text-white/35">+{events.length - 1}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="event-calendar-upcoming border-t border-white/8 px-3 py-2">
            <div className="flex items-center justify-center gap-2">
              <span className="h-px flex-1 bg-accent-cyan/18" />
              <span className="text-[9px] uppercase tracking-[0.28em] text-accent-cyan/54">
                upcoming
              </span>
              <span className="h-px flex-1 bg-accent-cyan/18" />
            </div>
            <div className="event-calendar-upcoming-list mt-2 grid gap-1 sm:grid-cols-2 xl:grid-cols-3">
              {sorted.slice(0, 6).map((event, index) => {
                const tone = toneOf(event.importance);
                return (
                  <button
                    key={event.id}
                    type="button"
                    onClick={() => setSelected(index)}
                    className="flex items-center gap-2 rounded border border-white/8 bg-white/[0.03] px-2 py-1.5 text-left text-[11px] hover:border-accent-cyan/30"
                  >
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: tone.color }} />
                    <span className="min-w-0 flex-1 truncate text-white/70">{event.title}</span>
                    <span className={tone.text}>{relativeLabel(event)}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </PanelFrame>
  );
}

function ActiveEvent({ event }: { event: Catalyst }) {
  const tone = toneOf(event.importance);
  const date = formatDay(eventDate(event));
  const notes = narrative(event);

  return (
    <div
      className="event-active-card relative overflow-hidden p-3"
      style={{
        background: `radial-gradient(circle at 0 0, ${tone.bg}, transparent 48%), linear-gradient(155deg, rgba(4,17,35,0.96), rgba(2,6,15,0.98))`,
      }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px" style={{ background: `linear-gradient(90deg, transparent, ${tone.color}, transparent)` }} />
      <div className="flex items-start gap-3">
        <div
          className="event-date-card grid h-[76px] w-[70px] shrink-0 place-items-center rounded-lg border"
          style={{ borderColor: `${tone.color}77`, background: tone.bg, boxShadow: `0 0 24px ${tone.bg}` }}
        >
          <div className="text-center">
            <div className="text-[10px] uppercase tracking-widest text-white/45">{date.month}</div>
            <div className={`font-display text-3xl leading-none ${tone.text}`}>{date.day}</div>
            <div className="text-[10px] text-white/45">{date.weekday}</div>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-widest ${tone.text}`} style={{ borderColor: `${tone.color}66`, background: tone.bg }}>
              {tone.label}
            </span>
            <span className="text-[10px] uppercase tracking-widest text-white/35">
              {event.region ?? "global"} / {relativeLabel(event)}
            </span>
          </div>
          <div className="mt-2 font-display text-base leading-snug text-white/92">{event.title}</div>
          {eventRiskText(event) ? (
            <div className="mt-2 rounded border border-white/10 bg-white/[0.03] px-2 py-1 text-[11px] text-white/60">
              {eventRiskText(event)}
            </div>
          ) : null}
        </div>
      </div>

      <div className="event-impact mt-3 border-t border-white/10 pt-3">
        <div className="text-[10px] uppercase tracking-widest text-white/38">Potential impact</div>
        <ul className="mt-2 space-y-1">
          {notes.map((note, index) => (
            <li key={index} className="flex gap-2 text-xs leading-5 text-white/66">
              <span style={{ color: tone.color }}>›</span>
              <span>{note}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function eventRiskText(event: Catalyst) {
  if (event.event_level === "NO_POSITION_INCREASE") return "New position increase is restricted around this event.";
  if (event.event_level === "WATCH") return "Watch window active; context can tighten risk posture.";
  return null;
}

const HORIZON_LABEL: Record<string, string> = { "15m": "15dk", "1h": "1sa", "4h": "4sa", "1d": "1g" };

function localTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleString("tr-TR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function untilLabel(minutes: number) {
  if (minutes < 60) return `${Math.max(0, Math.round(minutes))}dk`;
  if (minutes < 48 * 60) return `${Math.floor(minutes / 60)}sa ${Math.round(minutes % 60)}dk`;
  return `${Math.round(minutes / 1440)}g`;
}

/** Olay-sonrası takip: ne açıklandı, ne bekledik, ne oldu (salt-gözlem). */
function EventOutcomesStrip() {
  const { data } = useEventOutcomes();
  const recent = selectRecentEventOutcomes(data, Date.now());
  const next = selectNextEvent(data);
  if (!data || (!recent.length && !next)) return null;
  return (
    <div className="mb-3 space-y-2">
      {recent.map((rec) => (
        <OutcomeCard key={rec.id} rec={rec} horizons={data.horizons} />
      ))}
      {next ? (
        <div className="flex flex-wrap items-center gap-2 rounded border border-white/8 bg-white/[0.03] px-2 py-1.5 text-[11px] text-white/60">
          <span className="text-[9px] uppercase tracking-[0.2em] text-accent-cyan/60">sıradaki</span>
          <span className="text-white/80">{next.title}</span>
          <span>· {localTime(next.release_ts)}</span>
          <span className="text-accent-cyan/80">· {untilLabel(next.minutes_until)} sonra</span>
          {next.time_source === "default_noon" ? <span className="text-amber-300/70">(saat yaklaşık)</span> : null}
        </div>
      ) : null}
    </div>
  );
}

function OutcomeCard({ rec, horizons }: { rec: EventOutcomeRecord; horizons: EventOutcomesView["horizons"] }) {
  const tone = toneOf(rec.importance ?? undefined);
  const oc = rec.outcome;
  const decided = oc.direction === "low" || oc.direction === "high";
  const votes = decided ? oc.votes[oc.direction] ?? 0 : 0;
  const rows = selectOutcomeRows(rec, horizons);
  return (
    <div className="rounded-lg border bg-[#03101b]/92 p-3" style={{ borderColor: `${tone.color}55` }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[9px] uppercase tracking-[0.2em] text-accent-cyan/60">açıklandı</span>
        <span className="font-display text-sm text-white/90">{rec.title ?? rec.id}</span>
        <span className="text-[11px] text-white/45">{localTime(rec.release_ts)}</span>
        <span className="ml-auto rounded border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-white/50">
          {EVENT_OUTCOME_STATUS_LABEL[rec.status]}
        </span>
      </div>
      <div className="mt-2 text-xs text-white/75">
        Sonuç:{" "}
        <span className={decided ? "font-semibold text-accent-cyan" : "text-white/50"}>
          {oc.label ?? "henüz sonuç başlığı yok"}
        </span>
        {decided ? <span className="text-white/40"> · {votes} doğrulanmış başlık</span> : null}
      </div>
      {oc.headlines.length ? (
        <ul className="mt-1 space-y-0.5">
          {oc.headlines
            .filter((h) => h.vote !== "none")
            .slice(0, 2)
            .map((h, i) => (
              <li key={i} className="truncate text-[11px] text-white/45">› {h.title}</li>
            ))}
        </ul>
      ) : null}
      {rows.length ? (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-widest text-white/35">
                <th className="py-1 text-left font-normal">varlık</th>
                <th className="py-1 text-left font-normal">beklenen</th>
                {horizons.map((h) => (
                  <th key={h} className="py-1 text-right font-normal">{HORIZON_LABEL[h] ?? h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.symbol} className="border-t border-white/5">
                  <td className="py-1 text-white/75">{row.symbol}</td>
                  <td className="py-1 text-white/50">{row.expected > 0 ? "↑" : row.expected < 0 ? "↓" : "—"}</td>
                  {row.cells.map((c) => (
                    <td
                      key={c.horizon}
                      className={`py-1 text-right tabular-nums ${
                        c.mark === "hit" ? "text-emerald-300" : c.mark === "miss" ? "text-red-300" : "text-white/45"
                      }`}
                    >
                      {typeof c.move === "number" ? `${c.move > 0 ? "+" : ""}${c.move.toFixed(2)}%` : "·"}
                      {c.mark === "hit" ? " ✓" : c.mark === "miss" ? " ✗" : ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-1 text-[10px] text-white/35">
            Beklenen yön faiz kanalı varsayımı (salt-gözlem; karar zincirini değiştirmez).
            {rec.baseline_source === "snapshot_store" ? " Taban fiyat kayıtlı snapshot'tan." : ""}
          </div>
        </div>
      ) : null}
    </div>
  );
}
