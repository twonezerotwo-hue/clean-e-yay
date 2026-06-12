import type {
  DecisionMatrix,
  TimeframeDecision,
  Timeframe,
} from "@/types/generated/api";

export const MATRIX_TF_ORDER: Timeframe[] = ["15m", "1h", "4h", "1d", "1w"];

export type MatrixRow = { symbol: string; cells: TimeframeDecision[] };

/** symbol satırları × TF sırasına dizilmiş hücreler (frontend hesap yapmaz). */
export const selectMatrixRows = (m: DecisionMatrix | undefined): MatrixRow[] => {
  if (!m?.cells?.length) return [];
  const tfs = (m.timeframes?.length ? m.timeframes : MATRIX_TF_ORDER) as Timeframe[];
  return (m.symbols ?? []).map((symbol) => ({
    symbol,
    cells: tfs.flatMap((tf) => {
      const c = m.cells.find((x) => x.symbol === symbol && x.timeframe === tf);
      return c ? [c] : [];
    }),
  }));
};

export const selectMatrixSuspended = (m: DecisionMatrix | undefined) =>
  Boolean(m?.suspended);

export const selectMatrixRiskGate = (m: DecisionMatrix | undefined) =>
  m?.risk_gate;

/** P0 — matris event riski (hangi olay hücreleri kıstı; yalnızca kısıtlayıcı). */
export const selectMatrixEventRisk = (m: DecisionMatrix | undefined) =>
  m?.event_risk;

/** v2.7 D2 — matris türev özeti (banner). Yalnızca doğrulanmış + sıkışma riski
 * olanlar dikkat çeker; hücre etkisi cell.blocked_by="derivatives_risk:*". */
export const selectMatrixDerivatives = (m: DecisionMatrix | undefined) =>
  (m?.derivatives ?? []).filter(
    (d) => d.verified && d.squeeze_level !== "NONE",
  );

/** v2.7 D4 — matris realized vol özeti (banner). Yalnızca doğrulanmış + dikkat
 * çeken (ELEVATED/EXTREME rejim veya non-normal vol_state); hücre etkisi
 * cell.blocked_by="volatility_risk:*". */
export const selectMatrixVolatility = (m: DecisionMatrix | undefined) =>
  (m?.volatility ?? []).filter(
    (v) =>
      v.verified &&
      (v.regime === "ELEVATED" || v.regime === "EXTREME" || v.vol_state !== "normal"),
  );

/** v2.7 D5 — matris catalyst özeti (banner). Backend zaten yalnızca verified +
 * yarı-ömrü dolmamış + kısıtlayıcı catalyst'leri döner; hücre etkisi
 * cell.blocked_by="catalyst_risk:*". */
export const selectMatrixCatalysts = (m: DecisionMatrix | undefined) =>
  m?.catalysts ?? [];

/** Bir hücreyi hangi kapı kısıtlıyor → kısa, okunur etiket. */
export const cellBlockedLabel = (c: TimeframeDecision): string | undefined => {
  const tag = (c.blocked_by ?? [])[0];
  if (!tag) return undefined;
  if (tag.startsWith("risk_gate:")) return tag.replace("risk_gate:", "RISK ");
  if (tag.startsWith("mistake_memory")) return "MISTAKE";
  if (tag.startsWith("derivatives_risk")) return "TÜREV";
  if (tag.startsWith("volatility_risk")) return "VOLATİLİTE";
  if (tag.startsWith("catalyst_risk")) return "CATALYST";
  if (tag.startsWith("correlation")) return "KORELASYON";
  if (tag.startsWith("timeframe_policy")) return "TF BIAS";
  if (tag.includes("1w_bias")) return "1W BIAS";
  return tag;
};

export const selectMatrixDqsStatus = (m: DecisionMatrix | undefined) =>
  m?.dqs_status;

/** DecisionPanel mini strip — tek sembolün TF hücreleri. */
export const selectTfStripFor = (
  m: DecisionMatrix | undefined,
  symbol: string,
): TimeframeDecision[] =>
  selectMatrixRows(m).find((r) => r.symbol === symbol)?.cells ?? [];

/** İlk sembol (hero strip default'u). */
export const selectMatrixFirstSymbol = (
  m: DecisionMatrix | undefined,
): string | undefined => m?.symbols?.[0];
