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
