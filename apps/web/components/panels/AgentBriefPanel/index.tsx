"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief } from "@/lib/queries/hooks";
import {
  selectAgentBrief,
  AGENT_STATUS_TONE,
  AGENT_STATUS_LABEL,
  BLOCKER_TONE,
  DATA_MODE_TONE,
} from "@/lib/selectors/cockpit";
import { DIRECTION_COLOR } from "@/lib/constants";

// UX1 — ilk-ekran tek ana kart: agent şu an işlem açabilir mi, açamıyorsa
// ana sebep ne, ne izliyor. Tüm türetilmiş alanlar backend'den; frontend
// hesap yapmaz (DASHBOARD_RULES).

function Badge({ label, tone }: { label: string; tone: string }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-white/10 bg-white/5 ${tone}`}
    >
      {label}
    </span>
  );
}

export function AgentBriefPanel() {
  const { data, isLoading } = useCockpitBrief();
  if (isLoading) {
    return (
      <PanelFrame id="agent_brief">
        <PanelHeader title="Agent Brief" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const b = selectAgentBrief(data);
  if (!b) {
    return (
      <PanelFrame id="agent_brief">
        <PanelHeader title="Agent Brief" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const canAct = b.can_act;
  // UX4 — sert durdurucu (KILL_SWITCH/HALT/DQS/provider) ilk ekranda çok net
  // bir banner olarak görünür; ana engel backend main_blocker'dan (hesap yok).
  const isHardStop = ["HALT", "DQS_BLOCKED", "PROVIDER_DOWN"].includes(
    b.main_blocker.code,
  );
  return (
    <PanelFrame id="agent_brief">
      <PanelHeader
        title="Agent Brief"
        subtitle="agent'ın beyni — ne yapabilir, neden, ne izliyor"
        actions={
          <div className="flex flex-wrap items-center gap-1.5 justify-end">
            <Badge label={b.data_mode} tone={DATA_MODE_TONE[b.data_mode]} />
            <Badge
              label={canAct ? "CAN ACT" : "NO NEW ENTRY"}
              tone={canAct ? "text-signal-up" : "text-accent-magenta"}
            />
          </div>
        }
      />

      {/* UX4 — sert durdurucuda ilk ekranda yüksek-görünür uyarı bandı. */}
      {!canAct && b.main_blocker.code !== "NONE" ? (
        <div
          className={`mb-3 flex items-start gap-2 rounded-lg border px-3 py-2 ${
            isHardStop
              ? "border-signal-down/60 bg-signal-down/15"
              : "border-accent-magenta/50 bg-accent-magenta/10"
          }`}
        >
          <span className="text-base leading-none">{isHardStop ? "⛔" : "⚠"}</span>
          <div className="min-w-0">
            <div
              className={`text-sm font-semibold ${
                isHardStop ? "text-signal-down" : "text-accent-magenta"
              }`}
            >
              YENİ İŞLEM YOK — {b.main_blocker.label}
            </div>
            {b.main_blocker.detail ? (
              <div className="text-[11px] text-white/65 break-words">
                {b.main_blocker.detail}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Üst satır: agent durumu + ana engel */}
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/40">
            Agent Status
          </div>
          <div className={`text-3xl font-display mt-0.5 ${AGENT_STATUS_TONE[b.status]}`}>
            {AGENT_STATUS_LABEL[b.status] ?? b.status}
          </div>
        </div>
        <div className="min-w-[14rem]">
          <div className="text-[10px] uppercase tracking-widest text-white/40">
            Main Blocker
          </div>
          <div className={`text-lg font-medium mt-0.5 ${BLOCKER_TONE[b.main_blocker.code]}`}>
            {b.main_blocker.label}
          </div>
          {b.main_blocker.detail ? (
            <p className="text-[11px] text-white/55 mt-0.5">{b.main_blocker.detail}</p>
          ) : null}
        </div>
      </div>

      {/* Plain-language özet + önerilen duruş (tek bakışta çıkarım) */}
      <p className="text-sm text-white/85 leading-relaxed mt-3">{b.summary}</p>
      <div className="mt-2 inline-flex items-center gap-2 rounded-md border border-accent-cyan/30 bg-accent-cyan/5 px-2.5 py-1">
        <span className="text-[10px] uppercase tracking-widest text-accent-cyan/60">
          Önerilen duruş
        </span>
        <span className="text-xs font-medium text-accent-cyan/90">
          {b.recommended_stance}
        </span>
      </div>

      {/* Alt grid: durum metrikleri + adaylar + izleme */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div className="space-y-1.5 text-xs">
          <div className="text-[10px] uppercase tracking-widest text-white/40">
            Durum
          </div>
          <Row k="DQS" v={`${b.dqs?.status ?? "—"} (${b.dqs?.score?.toFixed?.(0) ?? "—"})`} />
          <Row k="Risk" v={b.risk?.action ?? "—"} />
          <Row k="Rejim" v={b.regime ?? "—"} />
          <Row k="Açık pozisyon" v={String(b.open_paper_positions ?? 0)} />
          {b.top_blockers?.length ? (
            <p className="text-[10px] text-white/40 pt-1">
              blockers: {b.top_blockers.slice(0, 3).join(" · ")}
            </p>
          ) : null}
        </div>

        <div className="space-y-1 text-xs">
          <div className="text-[10px] uppercase tracking-widest text-white/40">
            Top Candidates
          </div>
          {b.top_candidates?.length ? (
            <ul className="space-y-0.5">
              {b.top_candidates.slice(0, 5).map((c, i) => (
                <li key={i} className="flex items-center justify-between gap-2">
                  <span className="text-white/70">
                    {c.symbol} {c.timeframe}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className={DIRECTION_COLOR[c.direction ?? "neutral"]}>
                      {c.direction ?? "—"}
                    </span>
                    <span className="tabular-nums text-white/45">
                      {Math.round(c.score ?? 0)}
                    </span>
                    <span
                      className={
                        c.actionable ? "text-signal-up text-[10px]" : "text-white/35 text-[10px]"
                      }
                    >
                      {c.actionable ? "ACT" : "—"}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-white/40">aday yok</p>
          )}
        </div>

        <div className="space-y-1 text-xs">
          <div className="text-[10px] uppercase tracking-widest text-white/40">
            Next Watch
          </div>
          {b.next_watch_conditions?.length ? (
            <ul className="space-y-0.5 text-white/70">
              {b.next_watch_conditions.slice(0, 4).map((w, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-accent-cyan/70">›</span>
                  <span>{w.label}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-white/40">izlenecek koşul yok</p>
          )}
        </div>
      </div>
    </PanelFrame>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-white/45">{k}</span>
      <span className="text-white/85">{v}</span>
    </div>
  );
}
