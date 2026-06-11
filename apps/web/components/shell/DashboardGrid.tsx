import type { ReactNode } from "react";

/**
 * Pano grid'i. Tailwind CSS columns + responsive breakpoints. Her panel
 * span'ine göre yerleşir (1 / 2 / 3 / full).
 */
const SPAN: Record<string, string> = {
  "1": "lg:col-span-1",
  "2": "lg:col-span-2",
  "3": "lg:col-span-3",
  full: "lg:col-span-3",
};

export function DashboardGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 auto-rows-min">
      {children}
    </div>
  );
}

export function GridCell({
  span = "1",
  children,
}: {
  span?: "1" | "2" | "3" | "full";
  children: ReactNode;
}) {
  return <div className={SPAN[span]}>{children}</div>;
}
