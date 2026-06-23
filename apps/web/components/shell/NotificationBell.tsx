"use client";

import { useEffect, useRef, useState } from "react";

import {
  useAckAllNotifications,
  useAckNotification,
  useNotifications,
} from "@/lib/queries/hooks";
import type { Notification, NotificationPriority } from "@/types/generated/api";

function priorityColor(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "text-red-300 border-red-700/60";
    case "high":     return "text-orange-300 border-orange-700/60";
    case "medium":   return "text-amber-300 border-amber-700/60";
    case "low":      return "text-cyan-300 border-cyan-700/60";
  }
}

function relTime(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - t);
    const s = Math.round(diff / 1000);
    if (s < 60) return `${s}sn`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}dk`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}sa`;
    const d = Math.round(h / 24);
    return `${d}g`;
  } catch {
    return "?";
  }
}

function NotifRow({ n, onAck }: { n: Notification; onAck: (id: string) => void }) {
  const cls = priorityColor(n.priority);
  return (
    <div
      className={`px-3 py-2 border-l-2 ${cls} ${n.ack ? "opacity-50" : ""}`}
    >
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <div className="text-xs font-medium text-white/85 truncate">{n.title}</div>
        <div className="text-[10px] text-white/40 shrink-0 font-mono">{relTime(n.ts)}</div>
      </div>
      <div className="text-[11px] text-white/60 leading-snug">{n.body_short}</div>
      {!n.ack && (
        <button
          type="button"
          onClick={() => onAck(n.id)}
          className="text-[10px] font-mono text-accent-cyan/60 hover:text-accent-cyan mt-1"
        >
          okundu işaretle
        </button>
      )}
    </div>
  );
}

export function NotificationBell() {
  const { data } = useNotifications();
  const ackMutation = useAckNotification();
  const ackAllMutation = useAckAllNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const items: Notification[] = data?.notifications ?? [];
  const unread = data?.unread_count ?? 0;

  return (
    <div
      className="floating-notification-dock"
      data-open={open ? "true" : "false"}
      ref={ref}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="floating-notification-button"
        aria-label="Bildirimler"
      >
        <img
          src="/icons/eyay-notification-bell.png"
          alt=""
          className="floating-notification-image"
          draggable={false}
        />
        {unread > 0 && (
          <span className="floating-notification-badge">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="floating-notification-panel">
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
            <div className="text-[11px] font-mono uppercase tracking-widest text-white/70">
              Bildirimler · {unread} okunmamış
            </div>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => ackAllMutation.mutate()}
                className="text-[10px] font-mono text-accent-cyan/70 hover:text-accent-cyan"
              >
                hepsini okundu
              </button>
            )}
          </div>
          <div className="overflow-y-auto flex-1">
            {items.length === 0 ? (
              <div className="text-xs text-white/40 italic px-4 py-6 text-center">
                Henüz bildirim yok.
              </div>
            ) : (
              items.map((n) => (
                <NotifRow key={n.id} n={n} onAck={(id) => ackMutation.mutate(id)} />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
