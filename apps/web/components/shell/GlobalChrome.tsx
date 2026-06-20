"use client";

import { NotificationBell } from "./NotificationBell";
import { NotificationToast } from "./NotificationToast";

/** Tüm route'larda görünen global UI elemanları (bell + toast).
 *
 * Layout server component olduğu için bu client wrapper'a sarıyoruz —
 * NotificationBell react-query hook'larına bağlı, client-only olmalı.
 */
export function GlobalChrome() {
  return (
    <>
      <div className="fixed top-3 right-3 z-50">
        <NotificationBell />
      </div>
      <NotificationToast />
    </>
  );
}
