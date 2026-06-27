"use client";

import { useEventStream } from "@/hooks/useEventStream";
import { telemetry } from "@/lib/telemetry";

import { ErrorBoundary } from "./ErrorBoundary";
import { NotificationBell } from "./NotificationBell";
import { NotificationToast } from "./NotificationToast";

/** Tüm route'larda görünen global UI elemanları (bell + toast + SSE).
 *
 * Layout server component olduğu için bu client wrapper'a sarıyoruz —
 * NotificationBell react-query hook'larına bağlı, client-only olmalı.
 * useEventStream burada **tek bir kez** mount olur (tüm uygulama için
 * tek EventSource).
 */
export function GlobalChrome() {
  useEventStream();
  return (
    <ErrorBoundary
      fallback={null}
      onError={(error) => telemetry.panelCrashed("global_chrome", error)}
    >
      <NotificationBell />
      <NotificationToast />
    </ErrorBoundary>
  );
}
