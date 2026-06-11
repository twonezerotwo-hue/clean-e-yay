import type { ReactNode } from "react";

export function PanelHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-3 mb-3">
      <div>
        <h3 className="text-sm font-medium tracking-wide text-white/90">{title}</h3>
        {subtitle ? (
          <p className="text-xs text-white/50 mt-0.5">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
