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
