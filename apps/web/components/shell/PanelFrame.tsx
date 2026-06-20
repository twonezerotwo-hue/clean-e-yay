"use client";

import type { ReactNode } from "react";

import { telemetry } from "@/lib/telemetry";

import { ErrorBoundary } from "./ErrorBoundary";
import { QuantumPanelField, getQuantumPanelStyle } from "./QuantumPanelField";

// Shared frame for all panels: visual shell, error boundary, crash telemetry.
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
    <section
      id={id}
      data-panel={id}
      className={`panel quantum-panel ${className}`}
      style={getQuantumPanelStyle(id)}
    >
      <QuantumPanelField id={id} />
      <div className="relative z-10">
        <ErrorBoundary
          fallback={
            <div className="text-xs text-signal-down/80">
              Panel hata verdi - degrade modda render edilemedi.
            </div>
          }
          onError={(err) => telemetry.panelCrashed(id, err)}
        >
          {children}
        </ErrorBoundary>
      </div>
    </section>
  );
}
