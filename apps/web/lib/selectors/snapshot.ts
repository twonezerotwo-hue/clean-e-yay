import type {
  DataSnapshot,
  DerivativesSnapshot,
  OptionsSnapshot,
  ProviderStatus,
  TechnicalTf,
  Timeframe,
  VolatilitySnapshot,
} from "@/types/generated/api";

export const TF_ORDER: Timeframe[] = ["15m", "1h", "4h", "1d", "1w"];

// v2.7 D4 — realized volatility (symbol → TF sırasına dizilmiş hücreler).
// Frontend hesap yapmaz; backend snapshot'ını gösterir.
export const selectVolatility = (
  s: DataSnapshot | undefined,
): { symbol: string; cells: VolatilitySnapshot[] }[] => {
  const m = s?.volatility ?? {};
  return Object.entries(m)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([symbol, byTf]) => ({
      symbol,
      cells: TF_ORDER.flatMap((tf) => {
        const v = byTf[tf];
        return v ? [v] : [];
      }),
    }));
};

// v2.7 D2 — kripto türev snapshot'ları (symbol sırasına dizili). squeeze_proxy
// GERÇEK liquidation değildir (is_proxy). Frontend hesap yapmaz; backend
// ViewModel'ini gösterir.
export const selectDerivatives = (
  s: DataSnapshot | undefined,
): DerivativesSnapshot[] =>
  Object.values(s?.derivatives ?? {}).sort((a, b) =>
    a.symbol.localeCompare(b.symbol),
  );

// v2.7 D3 — options IV/skew/term snapshot'ları (symbol sırasına dizili). skew_25d
// GERÇEK greeks değildir (is_proxy). Frontend hesap yapmaz; backend ViewModel'i
// gösterir.
export const selectOptions = (
  s: DataSnapshot | undefined,
): OptionsSnapshot[] =>
  Object.values(s?.options ?? {}).sort((a, b) =>
    a.symbol.localeCompare(b.symbol),
  );

export const selectPrices = (s: DataSnapshot | undefined) => s?.prices ?? [];

export const selectDqs = (s: DataSnapshot | undefined) => s?.dqs;

export const selectFallbackProviders = (s: DataSnapshot | undefined) => {
  const ps = s?.provider_status ?? {};
  return Object.entries(ps)
    .filter(([, v]) => v.fallbacks > 0)
    .map(([name, v]) => ({ name, ...v }));
};

export const selectProviderList = (
  s: DataSnapshot | undefined,
): (ProviderStatus & { name: string })[] => {
  const ps = s?.provider_status ?? {};
  return Object.entries(ps).map(([name, v]) => ({ name, ...v }));
};

export const selectSnapshotMeta = (s: DataSnapshot | undefined) => s?.meta;

// T1 — symbol → TF sırasına dizilmiş teknik özetler (frontend hesap yapmaz).
export const selectTechnicalsByTf = (
  s: DataSnapshot | undefined,
): { symbol: string; tfs: TechnicalTf[] }[] => {
  const m = s?.technicals_by_tf ?? {};
  return Object.entries(m).map(([symbol, byTf]) => ({
    symbol,
    tfs: TF_ORDER.flatMap((tf) => {
      const t = byTf[tf];
      return t ? [t] : [];
    }),
  }));
};

export const selectTfTechnicalsFor = (
  s: DataSnapshot | undefined,
  symbol: string,
): TechnicalTf[] =>
  selectTechnicalsByTf(s).find((r) => r.symbol === symbol)?.tfs ?? [];

// SnapshotPanel kapsama satırı: kaç TF özeti OK / toplam.
export const selectTfCoverage = (
  s: DataSnapshot | undefined,
): { ok: number; total: number } | null => {
  const rows = selectTechnicalsByTf(s);
  if (!rows.length) return null;
  const all = rows.flatMap((r) => r.tfs);
  return { ok: all.filter((t) => t.status === "OK").length, total: all.length };
};
