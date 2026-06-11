"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { EmptyState } from "@/components/shell/EmptyState";

export function PatternsPanel() {
  return (
    <PanelFrame id="patterns">
      <PanelHeader title="Grafik Desenleri" subtitle="v2.2'de implement edilecek" />
      <EmptyState message="Pattern dedektörü v2.2-decision fazında bağlanacak." />
    </PanelFrame>
  );
}
