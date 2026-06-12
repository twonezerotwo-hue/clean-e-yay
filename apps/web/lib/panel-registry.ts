/**
 * Pano düzeni için tek doğruluk kaynağı. Her panel kayıtlı: id, başlık,
 * default visibility, grid span. Layout DashboardGrid bunu okur.
 */
export type PanelKey =
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
  | "timeframe_matrix";

export type PanelMeta = {
  id: PanelKey;
  title: string;
  defaultVisible: boolean;
  span: "1" | "2" | "3" | "full";
  group: "decision" | "evidence" | "data" | "learning" | "ops";
};

export const PANEL_REGISTRY: PanelMeta[] = [
  { id: "decision",         title: "Karar Merkezi",       defaultVisible: true,  span: "full", group: "decision" },
  { id: "risk_gate",        title: "Risk Kapısı",         defaultVisible: true,  span: "2",    group: "decision" },
  { id: "agent_votes",      title: "Agent Oyları",        defaultVisible: true,  span: "1",    group: "evidence" },
  { id: "position_checks",  title: "Pozisyon Kontrolleri",defaultVisible: true,  span: "3",    group: "evidence" },
  { id: "ai_report",        title: "AI Analist Raporu",   defaultVisible: true,  span: "2",    group: "decision" },
  { id: "chat",             title: "Sohbet",              defaultVisible: false, span: "1",    group: "ops" },
  { id: "command_signals",  title: "Komuta Sinyalleri",   defaultVisible: true,  span: "2",    group: "data" },
  { id: "event_calendar",   title: "Olay Takvimi",        defaultVisible: true,  span: "1",    group: "data" },
  { id: "scenario",         title: "Senaryo",             defaultVisible: true,  span: "1",    group: "data" },
  { id: "capital_rotation", title: "Sermaye Rotasyonu",   defaultVisible: true,  span: "3",    group: "data" },
  { id: "news",             title: "Haberler",            defaultVisible: true,  span: "2",    group: "data" },
  { id: "patterns",         title: "Grafik Desenleri",    defaultVisible: false, span: "1",    group: "data" },
  { id: "learning",         title: "Öğrenme",             defaultVisible: true,  span: "2",    group: "learning" },
  { id: "trading",          title: "Paper Trading",       defaultVisible: true,  span: "2",    group: "learning" },
  { id: "replay_status",    title: "Replay Durumu",       defaultVisible: false, span: "1",    group: "ops" },
  { id: "panel_audit",      title: "Pano Denetimi",       defaultVisible: false, span: "1",    group: "ops" },
  { id: "system_health",    title: "Sistem Sağlığı",      defaultVisible: true,  span: "full", group: "ops" },
  { id: "data_quality",     title: "Veri Kalitesi",        defaultVisible: true,  span: "2",    group: "data" },
  { id: "provider_status",  title: "Sağlayıcı Durumu",     defaultVisible: true,  span: "1",    group: "data" },
  { id: "snapshot",         title: "Snapshot",             defaultVisible: true,  span: "1",    group: "data" },
  { id: "market_data",      title: "Piyasa Verisi",        defaultVisible: true,  span: "2",    group: "data" },
  { id: "weight_proposal",  title: "Ağırlık Önerisi",      defaultVisible: true,  span: "2",    group: "learning" },
  { id: "weight_history",   title: "Ağırlık Geçmişi",      defaultVisible: true,  span: "1",    group: "learning" },
  { id: "calibration",      title: "Calibration",          defaultVisible: true,  span: "2",    group: "learning" },
  { id: "mistake_memory",   title: "Mistake Memory",       defaultVisible: true,  span: "1",    group: "learning" },
  { id: "correlation",      title: "Korelasyon",           defaultVisible: true,  span: "2",    group: "decision" },
  { id: "drawdown_guard",   title: "Drawdown Guard",       defaultVisible: true,  span: "1",    group: "decision" },
  { id: "timeframe_matrix", title: "Timeframe Matrisi",    defaultVisible: true,  span: "3",    group: "decision" },
];
