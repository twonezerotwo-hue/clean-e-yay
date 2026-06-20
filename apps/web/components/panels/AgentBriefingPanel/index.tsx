"use client";

import { useAgentBriefing } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";

type Tone = "ok" | "info" | "warn" | "alert";

const TONE_STYLE: Record<Tone, { dot: string; ring: string; text: string; label: string }> = {
  ok:    { dot: "bg-emerald-400", ring: "border-emerald-400/30", text: "text-emerald-300", label: "OK" },
  info:  { dot: "bg-sky-400",     ring: "border-sky-400/25",     text: "text-sky-300",     label: "BİLGİ" },
  warn:  { dot: "bg-amber-400",   ring: "border-amber-400/35",   text: "text-amber-300",   label: "DİKKAT" },
  alert: { dot: "bg-red-400",     ring: "border-red-500/45",     text: "text-red-300",     label: "UYARI" },
};

const CATEGORY_LABEL: Record<string, string> = {
  market:    "Piyasa",
  agent:     "Agent",
  risk:      "Risk",
  events:    "Olay",
  news:      "Haber",
  providers: "Sağlayıcı",
  alerts:    "Bildirim",
  system:    "Sistem",
};

/**
 * Raporcu Agent — Layer 0.
 *
 * Backend her cycle (30s) state'i tarar; bu panel başlık başlık özet gösterir.
 * Polling 15s + SSE tick.complete'te anında yenilenir. Karar vermez, sadece
 * "şu an ne oluyor"un insan-okunur özeti.
 */
export function AgentBriefingPanel() {
  const { data, isLoading, isError, dataUpdatedAt } = useAgentBriefing();
  const headlines = data?.headlines ?? [];
  const generatedAt = data?.generated_at;
  const regime = data?.regime_label;

  return (
    <section
      className="relative overflow-hidden rounded-2xl border border-accent-cyan/25 bg-gradient-to-br from-ink-900/95 via-ink-800/80 to-ink-900/95 p-5 shadow-[0_0_42px_rgba(34,211,238,0.12)] backdrop-blur"
      data-testid="agent-briefing"
    >
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-display text-lg uppercase tracking-[0.22em] text-accent-cyan">
            Raporcu Agent
          </h2>
          {regime ? (
            <span className="rounded-full border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest text-white/70">
              rejim · {regime}
            </span>
          ) : null}
        </div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-white/45">
          {isLoading
            ? "yükleniyor"
            : isError
              ? "bağlantı yok"
              : generatedAt
                ? `güncellendi ${fmtRelative(generatedAt)}`
                : `tick ${fmtRelative(new Date(dataUpdatedAt).toISOString())}`}
        </div>
      </header>

      {isError && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          Agent brief erişilemez. API ayakta mı? <code>/api/v1/agent/briefing</code>
        </div>
      )}

      {!isError && headlines.length === 0 && !isLoading && (
        <div className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-white/55">
          Henüz başlık yok. Bir sonraki cycle'da gelecek.
        </div>
      )}

      <ul className="space-y-2">
        {headlines.map((h, i) => {
          const style = TONE_STYLE[h.tone] ?? TONE_STYLE.info;
          const cat = CATEGORY_LABEL[h.category] ?? h.category;
          return (
            <li
              key={i}
              className={`group flex gap-3 rounded-xl border ${style.ring} bg-black/30 px-3 py-2.5 transition-colors hover:bg-black/40`}
            >
              <span
                className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${style.dot} shadow-[0_0_10px_currentColor]`}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span
                    className={`shrink-0 rounded border ${style.ring} ${style.text} px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-widest`}
                  >
                    {style.label}
                  </span>
                  <span className="shrink-0 text-[10px] font-mono uppercase tracking-widest text-white/40">
                    {cat}
                  </span>
                </div>
                <div className="mt-1 text-sm leading-snug text-white/90">{h.title}</div>
                {h.detail ? (
                  <div className="mt-0.5 text-[11px] leading-relaxed text-white/55">{h.detail}</div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>

      <footer className="mt-4 text-[10px] uppercase tracking-widest text-white/35">
        Karar vermez · 30sn cycle · auto-refresh · SSE tick.complete
      </footer>
    </section>
  );
}
