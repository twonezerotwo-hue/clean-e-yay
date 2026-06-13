/**
 * Pano düzeni için tek doğruluk kaynağı (information architecture). Her panel
 * kayıtlı: id, başlık, default visibility, grid span, IA grubu, tier.
 *
 * UX3 — IA grupları:
 *   simple (ilk ekran, önem sırası):
 *     command  → Agent Command Center (brief + karar + analist)
 *     risk     → Risk & Execution Freeze (gate/halt/paper)
 *     decision → Decision Trace / Candidate Matrix
 *     watch    → Watch Conditions
 *     chat     → Ask the Agent
 *   expert (collapsed, gruplu detay):
 *     data     → Data Quality & Providers
 *     market   → Market Structure
 *     macro    → Macro / Catalyst
 *     learning → Paper & Learning
 *     ops      → Ops / System
 *
 * Not: `group`/`tier` IA metadata'sıdır; layout `app/page.tsx`'te bu IA'ya göre
 * elle render edilir (yalnızca `defaultVisible` `usePanelVisibility` tarafından
 * okunur). Frontend hesap yapmaz — paneller mevcut selector/brief'i sunar.
 */
export type PanelKey =
  | "agent_brief"
  | "decision_trace"
  | "watch_conditions"
  | "paper_action"
  | "decision"
  | "risk_gate"
  | "agent_votes"
  | "position_checks"
  | "ai_report"
  | "chat"
  | "command_signals"
  | "event_calendar"
  | "scenario"
  | "capital_rotation"
  | "news"
  | "patterns"
  | "learning"
  | "trading"
  | "replay_status"
  | "panel_audit"
  | "system_health"
  | "data_quality"
  | "provider_status"
  | "snapshot"
  | "market_data"
  | "weight_proposal"
  | "weight_history"
  | "calibration"
  | "mistake_memory"
  | "correlation"
  | "drawdown_guard"
  | "crypto_derivatives"
  | "volatility"
  | "options_vol"
  | "catalyst_impact"
  | "timeframe_matrix";

export type PanelGroupId =
  // simple tier
  | "command"
  | "risk"
  | "decision"
  | "watch"
  | "chat"
  // expert tier
  | "data"
  | "market"
  | "macro"
  | "learning"
  | "ops";

export type PanelMeta = {
  id: PanelKey;
  title: string;
  defaultVisible: boolean;
  span: "1" | "2" | "3" | "full";
  group: PanelGroupId;
  tier: "simple" | "expert";
};

export const PANEL_REGISTRY: PanelMeta[] = [
  // ── SIMPLE — Agent Command Center ────────────────────────────────────────
  { id: "agent_brief",      title: "Agent Brief",          defaultVisible: true,  span: "full", group: "command",  tier: "simple" },
  { id: "decision",         title: "Karar Merkezi",        defaultVisible: true,  span: "2",    group: "command",  tier: "simple" },
  { id: "ai_report",        title: "AI Analist Raporu",    defaultVisible: true,  span: "1",    group: "command",  tier: "simple" },
  // ── SIMPLE — Risk & Execution Freeze ─────────────────────────────────────
  { id: "risk_gate",        title: "Risk Kapısı",          defaultVisible: true,  span: "2",    group: "risk",     tier: "simple" },
  { id: "drawdown_guard",   title: "Drawdown Guard",       defaultVisible: true,  span: "1",    group: "risk",     tier: "simple" },
  { id: "paper_action",     title: "Paper Action State",   defaultVisible: true,  span: "2",    group: "risk",     tier: "simple" },
  { id: "position_checks",  title: "Pozisyon Kontrolleri", defaultVisible: true,  span: "1",    group: "risk",     tier: "simple" },
  // ── SIMPLE — Decision Trace / Candidate Matrix ───────────────────────────
  { id: "timeframe_matrix", title: "Timeframe Matrisi",    defaultVisible: true,  span: "3",    group: "decision", tier: "simple" },
  { id: "decision_trace",   title: "Decision Trace",       defaultVisible: true,  span: "2",    group: "decision", tier: "simple" },
  { id: "agent_votes",      title: "Agent Kanıt Zinciri",  defaultVisible: true,  span: "1",    group: "decision", tier: "simple" },
  { id: "command_signals",  title: "Aday Sinyalleri",      defaultVisible: true,  span: "full", group: "decision", tier: "simple" },
  // ── SIMPLE — Watch Conditions ────────────────────────────────────────────
  { id: "watch_conditions", title: "İzlenecek Koşullar",   defaultVisible: true,  span: "full", group: "watch",    tier: "simple" },
  // ── SIMPLE — Ask the Agent ───────────────────────────────────────────────
  { id: "chat",             title: "Agent'a Sor",          defaultVisible: true,  span: "full", group: "chat",     tier: "simple" },

  // ── EXPERT — Data Quality & Providers ────────────────────────────────────
  { id: "data_quality",     title: "Veri Kalitesi",        defaultVisible: true,  span: "2",    group: "data",     tier: "expert" },
  { id: "provider_status",  title: "Sağlayıcı Durumu",     defaultVisible: true,  span: "1",    group: "data",     tier: "expert" },
  { id: "snapshot",         title: "Snapshot",             defaultVisible: true,  span: "1",    group: "data",     tier: "expert" },
  { id: "market_data",      title: "Piyasa Verisi",        defaultVisible: true,  span: "2",    group: "data",     tier: "expert" },
  { id: "panel_audit",      title: "Pano Denetimi",        defaultVisible: false, span: "1",    group: "data",     tier: "expert" },
  // ── EXPERT — Market Structure ────────────────────────────────────────────
  { id: "crypto_derivatives", title: "Kripto Türevleri",   defaultVisible: true,  span: "1",    group: "market",   tier: "expert" },
  { id: "volatility",       title: "Volatilite Rejimi",    defaultVisible: true,  span: "1",    group: "market",   tier: "expert" },
  { id: "options_vol",      title: "Options IV / Skew",    defaultVisible: true,  span: "1",    group: "market",   tier: "expert" },
  { id: "correlation",      title: "Korelasyon",           defaultVisible: true,  span: "2",    group: "market",   tier: "expert" },
  { id: "patterns",         title: "Grafik Desenleri",     defaultVisible: false, span: "1",    group: "market",   tier: "expert" },
  { id: "capital_rotation", title: "Sermaye Rotasyonu",    defaultVisible: true,  span: "full", group: "market",   tier: "expert" },
  // ── EXPERT — Macro / Catalyst ────────────────────────────────────────────
  { id: "catalyst_impact",  title: "Catalyst Etkisi",      defaultVisible: true,  span: "2",    group: "macro",    tier: "expert" },
  { id: "event_calendar",   title: "Olay Takvimi",         defaultVisible: true,  span: "1",    group: "macro",    tier: "expert" },
  { id: "news",             title: "Haberler",             defaultVisible: true,  span: "2",    group: "macro",    tier: "expert" },
  { id: "scenario",         title: "Senaryo",              defaultVisible: true,  span: "1",    group: "macro",    tier: "expert" },
  // ── EXPERT — Paper & Learning ────────────────────────────────────────────
  { id: "trading",          title: "Paper Trading",        defaultVisible: true,  span: "2",    group: "learning", tier: "expert" },
  { id: "learning",         title: "Öğrenme",              defaultVisible: true,  span: "1",    group: "learning", tier: "expert" },
  { id: "weight_proposal",  title: "Ağırlık Önerisi",      defaultVisible: true,  span: "2",    group: "learning", tier: "expert" },
  { id: "weight_history",   title: "Ağırlık Geçmişi",      defaultVisible: true,  span: "1",    group: "learning", tier: "expert" },
  { id: "calibration",      title: "Calibration",          defaultVisible: true,  span: "2",    group: "learning", tier: "expert" },
  { id: "mistake_memory",   title: "Mistake Memory",       defaultVisible: true,  span: "1",    group: "learning", tier: "expert" },
  // ── EXPERT — Ops / System ────────────────────────────────────────────────
  { id: "replay_status",    title: "Replay Durumu",        defaultVisible: false, span: "1",    group: "ops",      tier: "expert" },
  { id: "system_health",    title: "Sistem Sağlığı",       defaultVisible: true,  span: "full", group: "ops",      tier: "expert" },
];
