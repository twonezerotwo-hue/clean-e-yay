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
