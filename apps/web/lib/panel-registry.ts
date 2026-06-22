/**
 * Pano düzeni için tek doğruluk kaynağı (information architecture). Her panel
 * kayıtlı: id, başlık, default visibility, grid span, IA grubu, tier.
 *
 * UX4 — 3-tier IA:
 *   ANA (daima açık, tek-bakış operasyonel cockpit):
 *     hero    → Agent Brief
 *     command → Karar Merkezi + Analist (deterministik → neden)
 *     risk    → Risk & Yürütme (gate · drawdown · paper · seans)
 *     matrix  → Karar Matrisi (TF + Agent)
 *     watch   → İzlenecek Koşullar
 *     chat    → Agent'a Sor
 *   DETAY (collapsed, uzman bakışı):
 *     decision_detail → Karar İzi (trace · votes · shadow · checks · candidates)
 *     market          → Piyasa Yapısı (türev · vol · options · korelasyon · rotasyon)
 *     macro           → Makro & Catalyst (etki · takvim · haber · senaryo)
 *     learning        → Öğrenme & Kalibrasyon (paper · ağırlık · platt · TF)
 *   OPS (collapsed, default kapalı; sistem/veri):
 *     ops             → Data Quality · Provider · System Health · Replay · Audit
 *
 * Not: `group`/`tier` IA metadata'sıdır; layout `app/page.tsx`'te bu IA'ya göre
 * elle render edilir (yalnızca `defaultVisible` `usePanelVisibility` tarafından
 * okunur). Frontend hesap yapmaz — paneller mevcut selector/brief'i sunar.
 */
export type PanelKey =
  | "agent_narrator"
  | "risk_durumu"
  | "haberler_catalyst"
  | "trade_ticket"
  | "agent_brief"
  | "decision_trace"
  | "watch_conditions"
  | "paper_action"
  | "market_sessions"
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
  | "timeframe_matrix"
  | "agent_matrix"
  | "shadow"
  | "tf_weights";

export type PanelGroupId =
  // ana tier
  | "hero"
  | "ticket"
  | "command"
  | "risk"
  | "matrix"
  | "watch"
  | "chat"
  // detay tier
  | "decision_detail"
  | "market"
  | "macro"
  | "learning"
  // ops tier
  | "ops";

export type PanelTier = "ana" | "detay" | "ops";

export type PanelMeta = {
  id: PanelKey;
  title: string;
  defaultVisible: boolean;
  span: "1" | "2" | "3" | "full";
  group: PanelGroupId;
  tier: PanelTier;
};

export const PANEL_REGISTRY: PanelMeta[] = [
  // ── ANA — Hero (Agent Narrator) ──────────────────────────────────────────
  { id: "agent_narrator",   title: "Agent",                defaultVisible: true,  span: "full", group: "hero",            tier: "ana" },
  // ── ANA — Trade Ticket (broker handoff) ──────────────────────────────────
  { id: "trade_ticket",     title: "Trade Ticket",         defaultVisible: true,  span: "full", group: "ticket",          tier: "ana" },
  // ── ANA — Risk Durumu (RiskGate + Drawdown + Catalyst birleşik) ──────────
  { id: "risk_durumu",      title: "Risk Durumu",          defaultVisible: true,  span: "full", group: "risk",            tier: "ana" },
  // ── DETAY — Haberler & Catalyst (3 panel sekme) ──────────────────────────
  { id: "haberler_catalyst", title: "Haberler & Catalyst", defaultVisible: true,  span: "full", group: "macro",           tier: "detay" },
  // ── DETAY (eski) — Agent Brief (uzun-form, ANA'da Narrator var) ──────────
  { id: "agent_brief",      title: "Agent Brief (detay)",  defaultVisible: false, span: "full", group: "command",         tier: "detay" },
  // ── ANA — Komuta Merkezi ─────────────────────────────────────────────────
  { id: "decision",         title: "Karar Merkezi",        defaultVisible: true,  span: "2",    group: "command",         tier: "ana" },
  { id: "ai_report",        title: "AI Analist Raporu",    defaultVisible: true,  span: "1",    group: "command",         tier: "ana" },
  // ── ANA — Risk & Yürütme ─────────────────────────────────────────────────
  { id: "risk_gate",        title: "Risk Kapısı",          defaultVisible: true,  span: "2",    group: "risk",            tier: "ana" },
  { id: "drawdown_guard",   title: "Drawdown Guard",       defaultVisible: true,  span: "1",    group: "risk",            tier: "ana" },
  { id: "paper_action",     title: "Paper Action State",   defaultVisible: true,  span: "2",    group: "risk",            tier: "ana" },
  { id: "market_sessions",  title: "Piyasa Seansları",     defaultVisible: true,  span: "1",    group: "risk",            tier: "ana" },
  // ── ANA — Karar Matrisi ──────────────────────────────────────────────────
  { id: "timeframe_matrix", title: "Timeframe Matrisi",    defaultVisible: true,  span: "full", group: "matrix",          tier: "ana" },
  { id: "agent_matrix",     title: "Agent Matrisi",        defaultVisible: true,  span: "full", group: "matrix",          tier: "ana" },
  // ── ANA — İzlenecek Koşullar ─────────────────────────────────────────────
  { id: "watch_conditions", title: "İzlenecek Koşullar",   defaultVisible: true,  span: "full", group: "watch",           tier: "ana" },
  // ── ANA — Agent'a Sor ────────────────────────────────────────────────────
  { id: "chat",             title: "Agent'a Sor",          defaultVisible: true,  span: "full", group: "chat",            tier: "ana" },

  // ── DETAY — Karar İzi ────────────────────────────────────────────────────
  { id: "decision_trace",   title: "Decision Trace",       defaultVisible: true,  span: "2",    group: "decision_detail", tier: "detay" },
  { id: "agent_votes",      title: "Agent Kanıt Zinciri",  defaultVisible: true,  span: "1",    group: "decision_detail", tier: "detay" },
  { id: "shadow",           title: "Shadow Gözlem",        defaultVisible: true,  span: "full", group: "decision_detail", tier: "detay" },
  { id: "position_checks",  title: "Pozisyon Kontrolleri", defaultVisible: true,  span: "1",    group: "decision_detail", tier: "detay" },
  { id: "command_signals",  title: "Aday Sinyalleri",      defaultVisible: true,  span: "full", group: "decision_detail", tier: "detay" },
  // ── DETAY — Piyasa Yapısı ────────────────────────────────────────────────
  { id: "crypto_derivatives", title: "Kripto Türevleri",   defaultVisible: true,  span: "1",    group: "market",          tier: "detay" },
  { id: "volatility",       title: "Volatilite Rejimi",    defaultVisible: true,  span: "1",    group: "market",          tier: "detay" },
  { id: "options_vol",      title: "Options IV / Skew",    defaultVisible: true,  span: "1",    group: "market",          tier: "detay" },
  { id: "correlation",      title: "Korelasyon",           defaultVisible: true,  span: "2",    group: "market",          tier: "detay" },
  { id: "patterns",         title: "Grafik Desenleri",     defaultVisible: true,  span: "1",    group: "market",          tier: "detay" },
  { id: "capital_rotation", title: "Kuresel Likidite Rotasyonu", defaultVisible: true,  span: "full", group: "market",          tier: "detay" },
  // ── DETAY — Makro / Catalyst ─────────────────────────────────────────────
  { id: "catalyst_impact",  title: "Catalyst Etkisi",      defaultVisible: true,  span: "2",    group: "macro",           tier: "detay" },
  { id: "event_calendar",   title: "Olay Takvimi",         defaultVisible: true,  span: "1",    group: "macro",           tier: "detay" },
  { id: "news",             title: "Haberler",             defaultVisible: true,  span: "2",    group: "macro",           tier: "detay" },
  { id: "scenario",         title: "Senaryo",              defaultVisible: true,  span: "1",    group: "macro",           tier: "detay" },
  // ── DETAY — Öğrenme & Kalibrasyon ────────────────────────────────────────
  { id: "trading",          title: "Paper Trading",        defaultVisible: true,  span: "2",    group: "learning",        tier: "detay" },
  { id: "learning",         title: "Öğrenme",              defaultVisible: true,  span: "1",    group: "learning",        tier: "detay" },
  { id: "weight_proposal",  title: "Ağırlık Önerisi",      defaultVisible: true,  span: "2",    group: "learning",        tier: "detay" },
  { id: "weight_history",   title: "Ağırlık Geçmişi",      defaultVisible: true,  span: "1",    group: "learning",        tier: "detay" },
  { id: "calibration",      title: "Calibration",          defaultVisible: true,  span: "2",    group: "learning",        tier: "detay" },
  { id: "mistake_memory",   title: "Mistake Memory",       defaultVisible: true,  span: "1",    group: "learning",        tier: "detay" },
  { id: "tf_weights",       title: "tf_weights Kalibrasyon", defaultVisible: true, span: "2",   group: "learning",        tier: "detay" },

  // ── OPS — Sistem / Veri (default kapalı) ─────────────────────────────────
  { id: "data_quality",     title: "Veri Kalitesi",        defaultVisible: false, span: "2",    group: "ops",             tier: "ops" },
  { id: "provider_status",  title: "Sağlayıcı Durumu",     defaultVisible: false, span: "1",    group: "ops",             tier: "ops" },
  { id: "snapshot",         title: "Snapshot",             defaultVisible: false, span: "1",    group: "ops",             tier: "ops" },
  { id: "market_data",      title: "Piyasa Verisi",        defaultVisible: false, span: "2",    group: "ops",             tier: "ops" },
  { id: "panel_audit",      title: "Pano Denetimi",        defaultVisible: false, span: "1",    group: "ops",             tier: "ops" },
  { id: "system_health",    title: "Sistem Sağlığı",       defaultVisible: false, span: "full", group: "ops",             tier: "ops" },
  { id: "replay_status",    title: "Replay Durumu",        defaultVisible: false, span: "1",    group: "ops",             tier: "ops" },
];
