/**
 * Shadow selectors — backend ShadowComparison ViewModel → render-ready shapes.
 * Step 9 controlled activation (observation mode): the NEW agent pipeline runs in
 * shadow next to the live decide_matrix engine. Frontend does NO math — it only maps
 * the precomputed live-vs-shadow comparison to labels/tones. This is observe-only;
 * `affected_paper` is always false (the shadow never moves paper).
 */
import type {
  ShadowAgreement,
  ShadowComparison,
  ShadowRow,
} from "@/types/generated/api";

export const AGREEMENT_LABEL: Record<ShadowAgreement, string> = {
  AGREE_ENTRY: "UYUM · giriş",
  AGREE_FLAT: "UYUM · flat",
  DISAGREE_DIRECTION: "YÖN ÇELİŞKİSİ",
  LIVE_ONLY_ENTRY: "YALNIZ CANLI",
  SHADOW_ONLY_ENTRY: "YALNIZ SHADOW",
};

export function agreementTone(a?: string): string {
  switch (a) {
    case "AGREE_ENTRY":
      return "border-signal-up/50 text-signal-up bg-signal-up/10";
    case "DISAGREE_DIRECTION":
      return "border-signal-down/50 text-signal-down bg-signal-down/10";
    case "SHADOW_ONLY_ENTRY":
    case "LIVE_ONLY_ENTRY":
      return "border-amber-400/40 text-amber-300 bg-amber-400/10";
    default: // AGREE_FLAT / missing
      return "border-white/10 text-white/45";
  }
}

export function dirGlyph(dir?: string | null): string {
  if (dir === "long") return "▲";
  if (dir === "short") return "▼";
  return "·";
}

export function selectShadowRows(data?: ShadowComparison): ShadowRow[] {
  return data?.rows ?? [];
}

/** Ordered summary chips (label, count) from the per-tick agreement counts. */
export function agreementChips(
  data?: ShadowComparison,
): { key: ShadowAgreement; label: string; count: number }[] {
  const s = data?.summary;
  const order: ShadowAgreement[] = [
    "AGREE_ENTRY",
    "DISAGREE_DIRECTION",
    "SHADOW_ONLY_ENTRY",
    "LIVE_ONLY_ENTRY",
    "AGREE_FLAT",
  ];
  const map: Record<ShadowAgreement, number> = {
    AGREE_ENTRY: s?.agree_entry ?? 0,
    AGREE_FLAT: s?.agree_flat ?? 0,
    DISAGREE_DIRECTION: s?.disagree_direction ?? 0,
    LIVE_ONLY_ENTRY: s?.live_only_entry ?? 0,
    SHADOW_ONLY_ENTRY: s?.shadow_only_entry ?? 0,
  };
  return order.map((key) => ({ key, label: AGREEMENT_LABEL[key], count: map[key] }));
}

/** tf_weights trust verdict, one line (PRIOR/untrusted until calibration validates). */
export function trustSummary(data?: ShadowComparison): string {
  const c = data?.calibration;
  if (!c) return "tf_weights: —";
  if (c.tf_weights_trusted) {
    const tfs = c.calibrated_timeframes.join(", ") || "—";
    return `tf_weights: CALIBRATED (${tfs})`;
  }
  return "tf_weights: PRIOR · güvenilmiyor (kalibrasyon bekliyor)";
}
