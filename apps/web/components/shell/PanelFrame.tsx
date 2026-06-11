"use client";

import type { ReactNode } from "react";

import { ErrorBoundary } from "./ErrorBoundary";
import { telemetry } from "@/lib/telemetry";

/**
 * Tüm paneller için ortak çerçeve. ErrorBoundary + crash telemetri içeride.
 */
export function PanelFrame({
  id,
  className = "",
  children,
}: {
  id: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section data-panel={id} className={`panel ${className}`}>
      <ErrorBoundary
        fallback={
          <div className="text-xs text-signal-down/80">
            Panel hata verdi — degrade modda render edilemedi.
          </div>
        }
        onError={(err) => telemetry.panelCrashed(id, err)}
      >
        {children}
      </ErrorBoundary>
    </section>
  );
}
