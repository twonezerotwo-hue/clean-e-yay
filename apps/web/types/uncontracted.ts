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
