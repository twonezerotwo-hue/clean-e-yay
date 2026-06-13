/**
 * Pano düzeni için tek doğruluk kaynağı. Her panel kayıtlı: id, başlık,
 * default visibility, grid span. Layout DashboardGrid bunu okur.
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

export type PanelMeta = {
  id: PanelKey;
  title: string;
  defaultVisible: boolean;
  span: "1" | "2" | "3" | "full";
  group: "decision" | "evidence" | "data" | "learning" | "ops";
  // UX1 — ilk-ekran cockpit'i (simple) mi, ikinci-plan uzman paneli (expert) mi.
  tier: "simple" | "expert";
};

export const PANEL_REGISTRY: PanelMeta[] = [
  // UX1 — Agent Operating Cockpit (ilk ekran).
  { id: "agent_brief",      title: "Agent Brief",         defaultVisible: true,  span: "full", group: "decision", tier: "simple" },
  { id: "decision_trace",   title: "Decision Trace",      defaultVisible: true,  span: "2",    group: "decision", tier: "simple" },
  { id: "watch_conditions", title: "Watch / Trigger",     defaultVisible: true,  span: "1",    group: "decision", tier: "simple" },
  { id: "timeframe_matrix", title: "Timeframe Matrisi",   defaultVisible: true,  span: "3",    group: "decision", tier: "simple" },
  { id: "paper_action",     title: "Paper Action State",  defaultVisible: true,  span: "2",    group: "decision", tier: "simple" },
  { id: "chat",             title: "Agent'a Sor",         defaultVisible: true,  span: "1",    group: "ops",      tier: "simple" },
  { id: "decision",         title: "Karar Merkezi",       defaultVisible: true,  span: "full", group: "decision", tier: "expert" },
  // Uzman / Detaylar (ikinci plan — collapsed).
  { id: "risk_gate",        title: "Risk Kapısı",         defaultVisible: true,  span: "2",    group: "decision",  tier: "expert" },
  { id: "agent_votes",      title: "Agent Kanıt Zinciri", defaultVisible: true,  span: "1",    group: "evidence",  tier: "expert" },
  { id: "position_checks",  title: "Pozisyon Kontrolleri",defaultVisible: true,  span: "3",    group: "evidence",  tier: "expert" },
  { id: "ai_report",        title: "AI Analist Raporu",   defaultVisible: true,  span: "2",    group: "decision",  tier: "expert" },
  { id: "command_signals",  title: "Aday Sinyalleri",     defaultVisible: true,  span: "2",    group: "data",      tier: "expert" },
  { id: "event_calendar",   title: "Olay Takvimi",        defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "scenario",         title: "Senaryo",             defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "capital_rotation", title: "Sermaye Rotasyonu",   defaultVisible: true,  span: "3",    group: "data",      tier: "expert" },
  { id: "news",             title: "Haberler",            defaultVisible: true,  span: "2",    group: "data",      tier: "expert" },
  { id: "patterns",         title: "Grafik Desenleri",    defaultVisible: false, span: "1",    group: "data",      tier: "expert" },
  { id: "learning",         title: "Öğrenme",             defaultVisible: true,  span: "2",    group: "learning",  tier: "expert" },
  { id: "trading",          title: "Paper Trading",       defaultVisible: true,  span: "2",    group: "learning",  tier: "expert" },
  { id: "replay_status",    title: "Replay Durumu",       defaultVisible: false, span: "1",    group: "ops",       tier: "expert" },
  { id: "panel_audit",      title: "Pano Denetimi",       defaultVisible: false, span: "1",    group: "ops",       tier: "expert" },
  { id: "system_health",    title: "Sistem Sağlığı",      defaultVisible: true,  span: "full", group: "ops",       tier: "expert" },
  { id: "data_quality",     title: "Veri Kalitesi",        defaultVisible: true,  span: "2",    group: "data",      tier: "expert" },
  { id: "provider_status",  title: "Sağlayıcı Durumu",     defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "snapshot",         title: "Snapshot",             defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "market_data",      title: "Piyasa Verisi",        defaultVisible: true,  span: "2",    group: "data",      tier: "expert" },
  { id: "weight_proposal",  title: "Ağırlık Önerisi",      defaultVisible: true,  span: "2",    group: "learning",  tier: "expert" },
  { id: "weight_history",   title: "Ağırlık Geçmişi",      defaultVisible: true,  span: "1",    group: "learning",  tier: "expert" },
  { id: "calibration",      title: "Calibration",          defaultVisible: true,  span: "2",    group: "learning",  tier: "expert" },
  { id: "mistake_memory",   title: "Mistake Memory",       defaultVisible: true,  span: "1",    group: "learning",  tier: "expert" },
  { id: "correlation",      title: "Korelasyon",           defaultVisible: true,  span: "2",    group: "decision",  tier: "expert" },
  { id: "drawdown_guard",   title: "Drawdown Guard",       defaultVisible: true,  span: "1",    group: "decision",  tier: "expert" },
  { id: "crypto_derivatives", title: "Kripto Türevleri",   defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "volatility",       title: "Volatilite Rejimi",    defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "options_vol",      title: "Options IV / Skew",    defaultVisible: true,  span: "1",    group: "data",      tier: "expert" },
  { id: "catalyst_impact",  title: "Catalyst Etkisi",      defaultVisible: true,  span: "2",    group: "data",      tier: "expert" },
];
