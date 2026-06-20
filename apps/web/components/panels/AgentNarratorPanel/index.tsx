"use client";

/**
 * Agent Narrator — dashboard girişinin tek-bakış hero paneli.
 *
 * Üç katman:
 *   1. ANA SONUÇ   → cockpit_brief.agent_brief (status + main blocker + headline)
 *   2. TF ODAĞI    → agent_matrix → her TF için 4 symbol özeti
 *   3. GÜNDEM      → notifications (otomatik üretilen değişim akışı)
 *
 * Karar üretmez. Tüm veriler mevcut endpoint'lerden; saf gözlemci.
 */
import { useMemo, useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCockpitBrief, useNotifications, useRegimeReport } from "@/lib/queries/hooks";
import type { Notification, NotificationPriority } from "@/types/generated/api";

// ── Catalyst tarih + jargon sadeleştirme ─────────────────────────────────────

function fmtAbsDateTr(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const HH = String(d.getHours()).padStart(2, "0");
  const MM = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy}-${HH}:${MM}`;
}

/** Catalyst başlık fragmanlarını mutlak tarihe eşler. */
function buildCatalystDateMap(catalysts: any[] | undefined): Array<{ frag: string; date: string }> {
  if (!Array.isArray(catalysts)) return [];
  const out: Array<{ frag: string; date: string }> = [];
  for (const c of catalysts) {
    const dt = fmtAbsDateTr(c?.ts);
    if (!dt) continue;
    // Tam başlık VEYA başlığın anlamlı ilk parçası (örn. "FOMC Faiz Kararı")
    const title: string | undefined = c?.title;
    if (title) out.push({ frag: title, date: dt });
  }
  return out;
}

const JARGON_MAP: Array<[RegExp, string]> = [
  [/\bRiskGate\b/g, "Risk sistemi"],
  [/\bNO_POSITION_INCREASE\b/g, "yeni pozisyon açılışı kapalı"],
  [/\bRISK_REDUCE\b/g, "pozisyon azaltma önerisi"],
  [/\bKILL_SWITCH\b/g, "tüm girişler durdu"],
  [/\bALLOW_NORMAL\b/g, "açık"],
  [/\bWATCHING\b/gi, "izleme modunda"],
  [/\bDQS\b/g, "veri kalitesi"],
  // Çift parantez sadeleştir: "X (Y (Z): ...)" → "X — Y: ..."
  [/\(([^()]*?)\s*\(([^()]+?)\)\s*:\s*/g, "($1 — $2: "],
  // Sonu nokta+nokta → tek nokta
  [/\.\)\s*\./g, ".)"],
];

function enhanceText(
  raw: string | null | undefined,
  catalysts: any[] | undefined,
): string {
  if (!raw) return "";
  let text = raw;
  for (const [re, rep] of JARGON_MAP) text = text.replace(re, rep);
  // Catalyst başlıklarına mutlak tarih ekle (varsa)
  for (const { frag, date } of buildCatalystDateMap(catalysts)) {
    // İlk geçişte yanına (DD.MM.YYYY-HH:MM) ekle, zaten ekliyse atla
    const fragRe = new RegExp(
      `(${frag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})(?!\\s*\\(\\d{2}\\.)`,
      "g",
    );
    text = text.replace(fragRe, `$1 (${date})`);
  }
  return text;
}

// ── helpers ───────────────────────────────────────────────────────────────────

// ── helpers ───────────────────────────────────────────────────────────────────

function relTime(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - t);
    const s = Math.round(diff / 1000);
    if (s < 60) return `${s}sn önce`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}dk önce`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}sa önce`;
    const d = Math.round(h / 24);
    return `${d}g önce`;
  } catch {
    return "?";
  }
}

function priorityDot(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "bg-red-400";
    case "high":     return "bg-orange-400";
    case "medium":   return "bg-amber-400";
    case "low":      return "bg-cyan-400";
  }
}

function priorityText(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "text-red-300";
    case "high":     return "text-orange-300";
    case "medium":   return "text-amber-300";
    case "low":      return "text-cyan-300";
  }
}

// ── ANA SONUÇ ─────────────────────────────────────────────────────────────────

function MainConclusion({ brief, catalysts }: { brief: any; catalysts: any[] | undefined }) {
  if (!brief) {
    return <p className="text-sm text-white/50">Agent durumu yükleniyor…</p>;
  }
  const blocker = brief.main_blocker;
  const headline = enhanceText(brief.headline ?? brief.summary ?? "—", catalysts);
  const blockerLabel = enhanceText(blocker?.label ?? blocker?.code ?? "", catalysts);
  const blockerReason = enhanceText(blocker?.reason ?? "", catalysts);
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-3">
        <span className="text-[10px] uppercase tracking-widest text-white/40">Ana sonuç</span>
        <span className="text-base font-semibold text-white/95 leading-snug">
          {headline}
        </span>
      </div>
      {blocker && blocker.code !== "NONE" ? (
        <div className="text-[11px] text-white/60 leading-snug">
          <span className="text-orange-300">⚠ Engel:</span>{" "}
          {blockerLabel}
          {blockerReason ? ` — ${blockerReason}` : ""}
        </div>
      ) : null}
    </div>
  );
}

// ── GÜNDEM (notification feed) ────────────────────────────────────────────────

function ChangeFeed({
  notifications, expanded, catalysts,
}: {
  notifications: Notification[]; expanded: boolean; catalysts: any[] | undefined;
}) {
  const items = expanded ? notifications.slice(0, 20) : notifications.slice(0, 5);
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-3">
        <span className="text-[10px] uppercase tracking-widest text-white/40">Son değişimler</span>
        <span className="text-[10px] font-mono text-white/30">
          otomatik gündem · {notifications.length} kayıt
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] text-white/30 italic">Henüz değişim yok — sistem stabil.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((n) => (
            <li key={n.id} className="flex items-start gap-2 text-xs">
              <span className={`mt-1 h-1.5 w-1.5 rounded-full shrink-0 ${priorityDot(n.priority)}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="text-[10px] font-mono text-white/40 shrink-0">{relTime(n.ts)}</span>
                  <span className={`text-[12px] font-medium truncate ${priorityText(n.priority)}`}>
                    {enhanceText(n.title, catalysts)}
                  </span>
                </div>
                <div className="text-[11px] text-white/55 leading-snug">
                  {enhanceText(n.body_short, catalysts)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function AgentNarratorPanel() {
  const { data: briefData, isLoading: briefLoading } = useCockpitBrief();
  const { data: notifData } = useNotifications();
  const { data: regimeData } = useRegimeReport();
  const [expanded, setExpanded] = useState(false);

  const notifications: Notification[] = useMemo(
    () => notifData?.notifications ?? [],
    [notifData],
  );
  const catalysts: any[] | undefined = (regimeData as any)?.catalysts;

  if (briefLoading) {
    return (
      <PanelFrame id="agent_narrator">
        <PanelHeader title="Agent" subtitle="şu an ne oluyor" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const brief = briefData?.agent_brief;
  return (
    <PanelFrame id="agent_narrator">
      <PanelHeader
        title="Agent"
        subtitle="şu an ne oluyor — otomatik gündem"
        actions={
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] font-mono text-accent-cyan/70 hover:text-accent-cyan"
          >
            {expanded ? "▴ kısa görünüm" : "▾ tüm gündem"}
          </button>
        }
      />
      <div className="space-y-5">
        <MainConclusion brief={brief} catalysts={catalysts} />
        <div className="h-px bg-white/10" />
        <ChangeFeed notifications={notifications} expanded={expanded} catalysts={catalysts} />
      </div>
    </PanelFrame>
  );
}
