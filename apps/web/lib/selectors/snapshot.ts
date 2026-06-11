import type { DataSnapshot, ProviderStatus } from "@/types/generated/api";

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
