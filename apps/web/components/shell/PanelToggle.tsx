"use client";

import { useState, type ReactNode } from "react";

import { ErrorBoundary } from "./ErrorBoundary";

type View = { id: string; label: string };

/**
 * Tek, jenerik panel kabuğu. Eski projede 7 PanelShell vardı; çoğu sadece
 * iki view arasında geçiş yapıyordu. Burada tek bileşen, görünüm listesi
 * prop. ErrorBoundary içeride sarılı.
 */
export function PanelToggle({
  title,
  views,
  defaultView,
  children,
}: {
  title: string;
  views: View[];
  defaultView?: string;
  children: (activeView: string) => ReactNode;
}) {
  const [active, setActive] = useState(defaultView ?? views[0]?.id);

  return (
    <section className="panel flex flex-col gap-3">
      <header className="flex items-center justify-between">
        <h3 className="text-sm font-medium tracking-wide text-white/80">
          {title}
        </h3>
        <div className="flex items-center gap-1 text-xs">
          {views.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setActive(v.id)}
              className={`rounded-md px-2 py-1 transition ${
                active === v.id
                  ? "bg-accent-cyan/20 text-accent-cyan"
                  : "text-white/50 hover:text-white/80"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </header>
      <ErrorBoundary
        fallback={
          <div className="text-xs text-signal-down/80">
            Panel hata verdi — degrade modda render edilemedi.
          </div>
        }
      >
        <div className="min-h-[8rem]">{children(active!)}</div>
      </ErrorBoundary>
    </section>
  );
}
