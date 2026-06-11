export const fmtUSD = (v: number | null | undefined, digits = 0) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: digits,
      }).format(v);

export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toFixed(digits);

export const fmtTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
};

export const fmtRelative = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}sn önce`;
  if (sec < 3600) return `${Math.round(sec / 60)}dk önce`;
  if (sec < 86400) return `${Math.round(sec / 3600)}sa önce`;
  return `${Math.round(sec / 86400)}g önce`;
};
