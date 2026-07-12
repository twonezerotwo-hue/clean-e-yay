/**
 * Sözleşmesiz (observe-only) görünüm tipleri.
 *
 * `types/generated/api.ts` codegen çıktısıdır (elle düzenlenmez). Salt-gözlem
 * öğrenme endpoint'lerinin bir kısmı henüz codegen sözleşmesine girmedi; bunlar
 * BURADA elle, "observe-only friendly" olarak tutulur (DiscoveryPanel/Backtest
 * deseninin uncontracted karşılığı). Panel HESAP YAPMAZ; alanlar backend
 * viewmodel'iyle bire bir, bilinen-uncontracted.
 *
 * Buraya eklenen her tip = canlıya dokunmayan bir gözlem endpoint'i.
 */

// I2 — olgunluk damgası (maturity_gate.assess çıktısı).
export interface EvidenceMaturity {
  level: number; // 0-3
  maturity: string; // INSUFFICIENT | OBSERVED | PROPOSABLE | ACTIONABLE
  reason: string;
  ready_to_propose: boolean;
  ready_to_autotune: boolean;
}

// I1 — normalize kanıt kaydı (evidence_bus.EvidenceRecord).
export interface EvidenceRecord {
  topic: string;
  subject: string;
  source: string; // live | shadow | backtest
  regime: string | null;
  timeframe: string | null;
  n_samples: number | null;
  statistic: number | null;
  verdict: string | null;
  maturity: EvidenceMaturity | null;
  detail: Record<string, unknown>;
}

// I1 — Kanıt Otobüsü görünümü (GET /learning/evidence-bus).
export interface EvidenceBusView {
  generated_at: string;
  total: number;
  by_source: Record<string, number>;
  by_topic: Record<string, number>;
  by_verdict: Record<string, number>;
  by_maturity: Record<string, number>;
  records: EvidenceRecord[];
  note: string;
}

// D5 — Sinyal karnesi satırı (subsignal_scorecard v2, sinyal × TF).
export interface SubsignalRow {
  n: number;
  edge_pct: number;
  hit_rate: number;
  edge_ratio: number;
  edge_first_half: number;
  edge_second_half: number;
  stable: boolean;
  beats_baseline: boolean;
  verdict: string; // EDGE | FLAT | INVERSE | INSUFFICIENT
}

// D5 — TF bloğu (tipik hareket + taban çizgisi + sinyaller).
export interface SubsignalTf {
  horizon_bars: number;
  symbols_used: number;
  points: number;
  typical_move_pct: number;
  baseline_edge_pct: number;
  signals: Record<string, SubsignalRow>;
}

// D5 — Sinyal karnesi görünümü (GET /learning/subsignal-scorecard).
export interface SubsignalScorecardView {
  status: string; // OK | NO_DATA
  enabled: boolean;
  generated_at?: string;
  engine?: string;
  universe_n?: number;
  per_timeframe?: Record<string, SubsignalTf>;
  note?: string;
}

// Y-5 — meta-label kapısı: dominant×TF kovası bariyer-kalite tarihçesi.
export interface MetaGateBucket {
  n: number;
  good: number;
  bad: number;
  quality: Record<string, number>;
  quality_score: number; // (good − bad) / n ∈ [−1, +1]
}

// Y-5 — gölge seçicilik: verdict başına gerçekleşen sonuç toplamı.
export interface MetaGateVerdictStat {
  n: number;
  wins: number;
  pnl: number;
  win_rate: number | null;
}

// Y-5 — meta-label kapısı görünümü (GET /learning/meta-gate). SALT-GÖLGE:
// hüküm karara/boyuta uygulanmaz; scorecard aktivasyonun tek meşru dayanağı.
export interface MetaGateView {
  status: string; // OK | NO_TABLE
  shadow_only: boolean;
  generated_at?: string | null;
  buckets: Record<string, MetaGateBucket>;
  config: { min_score: number; min_bucket_n: number };
  scorecard: {
    by_verdict: { TAKE: MetaGateVerdictStat; SKIP: MetaGateVerdictStat };
    unmatched: number;
    selective: boolean;
    note?: string;
  };
}

// Çıkış backtest — tek exit-config satırı (ızgara noktası).
export interface ExitBacktestConfig {
  sl_mult: number;
  trail_act: number;
  trail_dist: number;
  ptp_trigger: number;
  ptp_frac: number;
  net_r: number;
  avg_r: number;
  median_r: number;
  win_rate: number;
  per_tf_avg_r: Record<string, number>;
}

// Çıkış backtest — TF başına en verimli config.
export interface ExitBacktestTfBest {
  sl_mult: number;
  trail_act: number;
  trail_dist: number;
  ptp: string;
  avg_r: number;
}

// Çıkış stop-verim backtest görünümü (GET /learning/exit-backtest). Salt-analiz:
// en verimli sabit+trailing stop aralığı; canlı çıkışa dokunmaz.
export interface ExitBacktestView {
  status: string; // OK | NO_DATA
  shadow_only: boolean;
  generated_at?: string | null;
  entry_count: number;
  tf_counts: Record<string, number>;
  best_configs: ExitBacktestConfig[];
  marginal: {
    sl_mult?: Record<string, number>;
    trail_act?: Record<string, number>;
    trail_dist?: Record<string, number>;
    ptp?: Record<string, number>;
  };
  per_tf_best: Record<string, ExitBacktestTfBest>;
}

// 0-2 tam-strateji gölge karnesi — tek hücre (TF×pivot×grup).
export interface ZeroTwoStrategyCell {
  label: string; // "tf|rightN|grup"
  tf: string;
  n: number;
  win_pct: number;
  ilk_total_r: number;
  hm_total_r: number;
  reentry_n: number;
  reentry_win: number;
  real_wick: boolean; // gerçek fitilli (en güvenilir) mi
}

// 0-2 tam-strateji gölge karnesi görünümü (GET /learning/zero-two-strategy).
// Owner nihai LONG akışı + sabit-bahis house-money; canlıya dokunmaz (salt-analiz).
export interface ZeroTwoStrategyView {
  status: string; // OK | NO_DATA
  shadow_only?: boolean;
  generated_at?: string | null;
  engine?: string;
  cells: ZeroTwoStrategyCell[];
  flat_note: string[];
}

// Konsey karnesi — istatistik hücresi (n + isabet + R + PnL).
export interface CouncilStats {
  n: number;
  win_pct: number | null;
  avg_r: number | null;
  total_r: number | null;
  total_pnl: number;
}

// Konsey karnesi — modül yayılımı satırı (güçlü-vs-zayıf isabet farkı).
export interface CouncilSpread {
  module: string;
  median: number;
  strong: CouncilStats;
  weak: CouncilStats;
  win_spread: number;
}

// Konsey karnesi görünümü (GET /learning/council). Katmanlar-arası kombinasyon
// analizi; sanki-filtreler veriden türetilir. IN-SAMPLE kanıt — kapı değildir.
export interface CouncilView {
  status: string; // OK | INSUFFICIENT | NO_DATA
  shadow_only?: boolean;
  generated_at?: string | null;
  n: number;
  min_rows?: number;
  baseline?: CouncilStats;
  module_spreads?: CouncilSpread[];
  pairs?: ({ pair: string } & CouncilStats)[];
  regimes?: ({ regime: string } & CouncilStats)[];
  conf_bands?: ({ band: string } & CouncilStats)[];
  what_if?: ({ filter: string; kept_pct: number } & CouncilStats)[];
}

// Aday bölge önericisi — tek confluence bölgesi (owner kesişim yöntemi, mekanik geometri).
export interface ZoneProposerZone {
  low: number;
  high: number;
  mid: number;
  confluence: number; // kaç BAĞIMSIZ araç bu bölgede kesişiyor
  sources: string[];
  dist_pct: number; // fiyata uzaklık (%)
  side: string; // "altında" | "üstünde"
  at?: string | null; // çizgi-kesişim tarihi (varsa)
  verdict: string; // "onayli" (owner iptal etmedikçe) | "iptal"
}

// Aday bölge önericisi — asset satırı (GET /learning/zone-proposer).
export interface ZoneProposerAsset {
  symbol: string;
  price_now?: number | null;
  weekly_bars?: number;
  top_confluence: number;
  zones: ZoneProposerZone[];
}

// Aday bölge önericisi görünümü. Makine ADAY önerir, bölge SEÇMEZ; owner iptal
// edene kadar onaylı. Canlı SL/TP etkisi zone_influence flag'ine bağlı (default OFF).
export interface ZoneProposerView {
  status: string; // OK | NO_DATA
  shadow_only?: boolean;
  generated_at?: string | null;
  engine?: string;
  honesty?: string;
  assets: ZoneProposerAsset[];
}

// Faz-A (EV kapısı) — per-hücre payoff EV R-örnek hazırlık satırı.
export interface PayoffReadinessRow {
  cell: string; // "tf|rejim"
  win_r_n: number;
  loss_r_n: number;
  min_r_samples: number;
  payoff_ready: boolean;
  short_by: number; // eşiğe kalan (0 = hazır)
}

// Faz-A — payoff EV hazırlık görünümü (GET /learning/payoff-readiness). Salt-
// gözlem: hangi hücre gerçekleşen-R payoff EV'sine geçecek kadar örnek gördü.
export interface PayoffReadinessView {
  status: string; // OK | NO_DATA
  shadow_only: boolean;
  payoff_weighted: boolean;
  min_r_samples: number;
  cell_count: number;
  ready_count: number;
  ready_cells: string[];
  closest_cell: PayoffReadinessRow | null;
  per_cell: PayoffReadinessRow[];
}

// Faz-A (Kalibrasyon) — per-TF Platt fit güven satırı.
export interface CalibrationFitRow {
  timeframe: string;
  fit_status: string; // fitted | insufficient | identity
  fit_samples: number;
  fitted_at: string | null;
  outcome_trust: string; // CALIBRATED | PRIOR
  outcome_n: number;
}

// Faz-A — per-TF fit güven görünümü (GET /learning/calibration-fit). Salt-gözlem:
// hangi TF'in kalibrasyonu güvenilir (fitted) vs örnek bekliyor (insufficient).
export interface CalibrationFitView {
  status: string; // OK | NO_DATA
  shadow_only: boolean;
  tf_platt_enabled: boolean;
  min_trades_per_tf: number;
  per_timeframe_fit: CalibrationFitRow[];
  fitted_timeframes: string[];
  any_fitted: boolean;
}

// Y-6 — haber olay-çalışması: kaynak×sentiment kovası ileri-getiri karnesi.
export interface NewsEventBucket {
  n: number;
  hits: number;
  sum_dir_return: number;
  avg_dir_return_pct: number; // yön-hizalı ortalama N-bar getiri (%)
  hit_rate: number | null;
  verdict: string; // PREDICTIVE | NO_EDGE | INSUFFICIENT
}

// Y-6 — haber olay-çalışması görünümü (GET /learning/news-event-study). SALT-
// GÖZLEM: hiçbir çıktı karara/ağırlığa dokunmaz; kanıtsızsa global UNPROVEN.
export interface NewsEventStudyView {
  status: string; // OK | NO_TABLE
  shadow_only: boolean;
  generated_at?: string | null;
  horizon_bars: number;
  events_total: number;
  matured: number;
  pending: number;
  buckets: Record<string, NewsEventBucket>;
  global_verdict: string; // PREDICTIVE | UNPROVEN
  config: { min_bucket_n: number };
}

// R4 — v2 gölge: sembol başına rejim-anahtarlı yön (tf_scoring_shadow artifact).
export interface TfScoringShadowSymbol {
  status: string; // OK | no_evidence | ERROR:*
  direction?: number | null;
  bias?: string; // BULLISH | BEARISH | NEUTRAL | NONE
  regime?: { regime: string; er: number } | null;
  direction_blend_legacy?: number | null;
  tf_scores?: Record<string, number>;
  tf_scores_legacy?: Record<string, number>;
  drivers?: Record<string, Record<string, { lean: number; weight: number }>>;
}

// R4 — v2 gölge görünümü (GET /learning/tf-scoring-shadow).
export interface TfScoringShadowView {
  status: string; // OK | NO_DATA
  enabled: boolean;
  generated_at?: string;
  engine?: string;
  scorecard_engine?: string | null;
  symbols_scored?: number;
  per_symbol?: Record<string, TfScoringShadowSymbol>;
  note?: string;
}

// R5 — yarış defteri: bir tasarımın (yeni beyin / kontrol / taban) puanı.
export interface TfScoringRaceDesign {
  decisive: number;
  hits: number;
  hit_rate?: number | null;
  avg_return_pct?: number | null;
}

// R5 — terfi kapıları (rail count/wilson/beats-baseline; her biri pass taşır).
export interface TfScoringRaceChecks {
  resolved_decisive?: { value: number; required: number; pass: boolean };
  ci_disjoint?: {
    new_brain_hit_rate?: number | null;
    wilson_low?: number;
    wilson_high?: number;
    pass: boolean;
  };
  beats_baseline?: {
    new_avg_return_pct?: number | null;
    baseline_avg_return_pct?: number | null;
    pass: boolean;
  };
}

// R5 — gölge yarış raporu (GET /learning/tf-scoring-race). Frontend HESAP YAPMAZ.
export interface TfScoringRaceView {
  status: string; // zarf: OK | NO_DATA
  enabled: boolean;
  race_status?: string; // terfi: READY | NOT_READY
  generated_at?: string;
  engine?: string;
  ledger_rows?: number;
  resolved?: number;
  designs?: Record<string, TfScoringRaceDesign>; // new_brain | legacy | baseline
  per_regime?: Record<string, Record<string, TfScoringRaceDesign>>;
  beats_baseline?: boolean | null;
  beats_legacy?: boolean | null;
  checks?: TfScoringRaceChecks;
  config?: { min_resolved: number; neutral_band_pct: number };
  note?: string;
}
