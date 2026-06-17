// apps/web/lib/selectors/cockpit-diff.ts
import type { AgentBrief } from "@/types/generated/api";

// UX1 — tick-diff (frontend ref karşılaştırması, seçenek a).
// DOMAIN HESABI YOK: status / main_blocker / risk / dqs gibi anlam üreten
// alanların hepsi backend ViewModel'inden gelir. Bu modül yalnızca "hangi
// backend alanı değişti" sorusunu yanıtlar ve görsel önem (severity) atar —
// tıpkı cockpit.ts'teki ton haritaları gibi (yalnızca sunum). DASHBOARD_RULES.

export type ChangeSeverity = "INFO" | "WATCH" | "CAUTION" | "CRITICAL";

export type ChangeGroup =
  | "decision"
  | "risk_gate"
  | "data_trust"
  | "top_candidates"
  | "macro_catalyst"
  | "market_structure"
  | "paper_system"
  | "scenario_alert";

export type BriefChange = {
  severity: ChangeSeverity;
  group: ChangeGroup;
  title: string;
  before?: string | number | null;
  after?: string | number | null;
};

// Hangi alan değişince ne kadar yüksek sesle duyurulur — statik sunum tablosu
// (anlam değil, "ne kadar öne çıksın" kararı).
const SEV = {
  status: "CRITICAL",
  blocker: "CRITICAL",
  risk: "CAUTION",
  dqs: "CAUTION",
  dataMode: "WATCH",
  regime: "WATCH",
  candidate: "WATCH",
} satisfies Record<string, ChangeSeverity>;

function leader(b: AgentBrief): { sym?: string; score?: number } {
  const c = b.top_candidates?.[0];
  return { sym: c?.symbol, score: c?.score };
}

export function detectBriefChanges(
  prev: AgentBrief | undefined,
  curr: AgentBrief,
): BriefChange[] {
  if (!prev) return []; // ilk snapshot → baz alındı, değişim yok
  const out: BriefChange[] = [];

  if (prev.status !== curr.status) {
    out.push({
      severity: SEV.status, group: "decision",
      title: "Agent durumu değişti", before: prev.status, after: curr.status,
    });
  }
  if (prev.main_blocker?.code !== curr.main_blocker?.code) {
    out.push({
      severity: SEV.blocker, group: "decision",
      title: "Ana engel değişti",
      before: prev.main_blocker?.label, after: curr.main_blocker?.label,
    });
  }
  if ((prev.risk?.action ?? null) !== (curr.risk?.action ?? null)) {
    out.push({
      severity: SEV.risk, group: "risk_gate",
      title: "RiskGate değişti", before: prev.risk?.action, after: curr.risk?.action,
    });
  }
  if ((prev.dqs?.status ?? null) !== (curr.dqs?.status ?? null)) {
    out.push({
      severity: SEV.dqs, group: "data_trust",
      title: "Veri kalitesi (DQS) değişti",
      before: prev.dqs?.status, after: curr.dqs?.status,
    });
  }
  if (prev.data_mode !== curr.data_mode) {
    out.push({
      severity: SEV.dataMode, group: "data_trust",
      title: "Veri modu değişti", before: prev.data_mode, after: curr.data_mode,
    });
  }
  if ((prev.regime ?? null) !== (curr.regime ?? null)) {
    out.push({
      severity: SEV.regime, group: "macro_catalyst",
      title: "Rejim değişti", before: prev.regime, after: curr.regime,
    });
  }
  const pl = leader(prev);
  const cl = leader(curr);
  if (pl.sym !== cl.sym) {
    out.push({
      severity: SEV.candidate, group: "top_candidates",
      title: "Lider aday değişti", before: pl.sym, after: cl.sym,
    });
  } else if (
    pl.score != null && cl.score != null && Math.abs(pl.score - cl.score) >= 5
  ) {
    out.push({
      severity: SEV.candidate, group: "top_candidates",
      title: `Lider aday skoru değişti (${cl.sym ?? "—"})`,
      before: Math.round(pl.score), after: Math.round(cl.score),
    });
  }

  const rank: Record<ChangeSeverity, number> = {
    CRITICAL: 3, CAUTION: 2, WATCH: 1, INFO: 0,
  };
  return out.sort((a, b) => rank[b.severity] - rank[a.severity]);
}

export const CHANGE_SEVERITY_TONE: Record<ChangeSeverity, string> = {
  INFO: "text-white/50",
  WATCH: "text-accent-cyan",
  CAUTION: "text-amber-400",
  CRITICAL: "text-signal-down",
};
