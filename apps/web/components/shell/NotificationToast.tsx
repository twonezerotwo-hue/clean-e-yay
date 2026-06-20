"use client";

import { useEffect, useRef, useState } from "react";

import { useNotifications } from "@/lib/queries/hooks";
import type { Notification, NotificationPriority } from "@/types/generated/api";

const TOAST_TTL_MS = 6_000;

function bgFor(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "border-red-600/70 bg-red-950/80";
    case "high":     return "border-orange-600/70 bg-orange-950/80";
    case "medium":   return "border-amber-600/60 bg-amber-950/70";
    case "low":      return "border-cyan-700/60 bg-cyan-950/70";
  }
}

function iconFor(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "🚨";
    case "high":     return "🔔";
    case "medium":   return "⚠";
    case "low":      return "ℹ";
  }
}

export function NotificationToast() {
  const { data } = useNotifications();
  const seenIds = useRef<Set<string>>(new Set());
  const initialized = useRef(false);
  const [visible, setVisible] = useState<Notification[]>([]);

  useEffect(() => {
    const items: Notification[] = data?.notifications ?? [];
    if (!initialized.current) {
      // İlk yüklemede tüm mevcut bildirimleri "görüldü" say (toast spam'i önle).
      items.forEach((n) => seenIds.current.add(n.id));
      initialized.current = true;
      return;
    }
    // Yeni okunmamış bildirimleri (önceden görülmemiş) toast olarak göster.
    const newOnes = items.filter((n) => !n.ack && !seenIds.current.has(n.id));
    if (newOnes.length === 0) return;
    newOnes.forEach((n) => seenIds.current.add(n.id));
    setVisible((prev) => [...prev, ...newOnes].slice(-3));  // max 3 görünür

    // Her toast TTL_MS sonra düşer
    newOnes.forEach((n) => {
      setTimeout(() => {
        setVisible((prev) => prev.filter((x) => x.id !== n.id));
      }, TOAST_TTL_MS);
    });
  }, [data]);

  if (visible.length === 0) return null;
  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
      {visible.map((n) => (
        <div
          key={n.id}
          className={`pointer-events-auto rounded-xl border backdrop-blur-md px-4 py-3 shadow-2xl w-[340px] ${bgFor(n.priority)}`}
          role="status"
        >
          <div className="flex items-start gap-2">
            <span className="text-base shrink-0">{iconFor(n.priority)}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-white/95">{n.title}</div>
              <div className="text-[11px] text-white/70 mt-0.5 leading-snug">{n.body_short}</div>
            </div>
            <button
              type="button"
              onClick={() => setVisible((prev) => prev.filter((x) => x.id !== n.id))}
              className="text-white/40 hover:text-white/80 text-xs"
              aria-label="Kapat"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
