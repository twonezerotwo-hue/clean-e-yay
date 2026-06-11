/**
 * Hafif frontend telemetri. Şimdilik sadece console; gerçek backend
 * endpoint'i v2.6'da gelir (POST /api/v1/telemetry/panel-error).
 */
type Severity = "info" | "warn" | "error";

const log = (sev: Severity, scope: string, payload: Record<string, unknown>) => {
  // eslint-disable-next-line no-console
  console[sev === "error" ? "error" : sev === "warn" ? "warn" : "log"](
    `[telemetry:${scope}]`,
    payload,
  );
};

export const telemetry = {
  panelCrashed(panel: string, error: Error) {
    log("error", "panel-crash", { panel, message: error.message });
  },
  staleData(panel: string, ageSec: number) {
    log("warn", "stale-data", { panel, ageSec });
  },
  queryFailed(key: string, message: string) {
    log("warn", "query-failed", { key, message });
  },
};
