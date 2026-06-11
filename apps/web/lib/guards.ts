/**
 * Hafif runtime type guard'lar. Backend uyumsuzluk durumunda
 * panel'in crash etmemesi için ince koruma.
 */
export const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);

export const isNonEmptyArray = <T,>(v: unknown): v is T[] =>
  Array.isArray(v) && v.length > 0;

export const safeNumber = (v: unknown, fallback = 0): number =>
  typeof v === "number" && Number.isFinite(v) ? v : fallback;

export const safeString = (v: unknown, fallback = ""): string =>
  typeof v === "string" ? v : fallback;
