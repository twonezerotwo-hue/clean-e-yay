"use client";

import { useCallback, useState } from "react";

/**
 * Stub — v2.6'da owner feedback endpoint'i geldiğinde gerçek POST'a bağlanır.
 * Şimdilik UI gösterimi için yerel state tutar.
 */
type FeedbackType = "approve" | "reject" | "comment";

export function useOwnerFeedback() {
  const [pending, setPending] = useState(false);
  const submit = useCallback(
    async (type: FeedbackType, payload: Record<string, unknown>) => {
      setPending(true);
      // eslint-disable-next-line no-console
      console.log("[owner-feedback]", type, payload);
      await new Promise((r) => setTimeout(r, 150));
      setPending(false);
    },
    [],
  );
  return { submit, pending };
}
