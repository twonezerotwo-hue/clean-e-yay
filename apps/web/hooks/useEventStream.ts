"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { qk } from "@/lib/queries/keys";

/**
 * SSE — tek EventSource bağlantısı. Backend agent event'lerini push'lar,
 * burada ilgili react-query cache'leri invalidate edilir → panel'ler kendi
 * verilerini hemen yeniden çeker. Polling kapatılmıyor (fallback olarak
 * kalıyor); sadece dakikada 30+ boşa istek yerine event-driven çağrı.
 *
 * Aynı sayfada iki kere mount edilmesin diye GlobalChrome içinden bir kez
 * çağrılıyor.
 */
export function useEventStream() {
  const qc = useQueryClient();
  const retryRef = useRef(0);

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (cancelled) return;
      // Same-origin: Next rewrite /api/* → backend SSE endpoint.
      es = new EventSource("/api/v1/stream");

      es.addEventListener("open", () => {
        retryRef.current = 0;
      });

      es.addEventListener("tick.complete", () => {
        // Agent cycle bitti — UI durumunu canlı tutmak için en sıcak
        // panel verileri:
        qc.invalidateQueries({ queryKey: qk.cockpitBrief });
        qc.invalidateQueries({ queryKey: qk.systemHealth });
        qc.invalidateQueries({ queryKey: qk.dashboardState });
        qc.invalidateQueries({ queryKey: qk.paperTradingState });
        qc.invalidateQueries({ queryKey: qk.tradeTickets });
        qc.invalidateQueries({ queryKey: qk.decisionMatrix });
        qc.invalidateQueries({ queryKey: qk.agentMatrix });
        qc.invalidateQueries({ queryKey: qk.agentBriefing });
      });

      es.addEventListener("notification.new", () => {
        qc.invalidateQueries({ queryKey: qk.notifications });
      });

      es.addEventListener("error", () => {
        // Bağlantı koptu — exponential backoff (max 30sn).
        es?.close();
        es = null;
        if (cancelled) return;
        const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
        retryRef.current += 1;
        reconnectTimer = setTimeout(connect, delay);
      });
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      es?.close();
    };
  }, [qc]);
}
