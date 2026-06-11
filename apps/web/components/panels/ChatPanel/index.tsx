"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { EmptyState } from "@/components/shell/EmptyState";

export function ChatPanel() {
  return (
    <PanelFrame id="chat">
      <PanelHeader title="Sohbet" subtitle="v2.6'da agent'a bağlanacak" />
      <EmptyState message="LLM persona endpoint'leri v2.6'da gelecek." />
    </PanelFrame>
  );
}
