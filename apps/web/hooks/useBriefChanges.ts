// apps/web/hooks/useBriefChanges.ts
"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentBrief } from "@/types/generated/api";
import { detectBriefChanges, type BriefChange } from "@/lib/selectors/cockpit-diff";

// Seçenek (a): önceki AgentBrief'i ref'te tut, yeni snapshot gelince diff'le.
// Hook yalnızca "ne zaman diff'lerim"i yönetir; anlam üretimi yok. Son N
// değişimi oturum boyunca biriktirir (sekmeye dönünce son değişimler görünür).
// Sayfa yenilenirse ref sıfırlanır → ilk snapshot baz alınır (kasıtlı).

const MAX_FEED = 12;

export function useBriefChanges(
  brief: AgentBrief | undefined,
  generatedAt: string | undefined,
) {
  const prevRef = useRef<AgentBrief | undefined>(undefined);
  const lastKeyRef = useRef<string | undefined>(undefined);
  const [feed, setFeed] = useState<BriefChange[]>([]);

  useEffect(() => {
    if (!brief) return;
    // Aynı snapshot'ta tekrar çalışma (re-render guard).
    const key = generatedAt ?? brief.generated_at ?? brief.summary;
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;

    const changes = detectBriefChanges(prevRef.current, brief);
    prevRef.current = brief;
    if (changes.length) {
      setFeed((f) => [...changes, ...f].slice(0, MAX_FEED));
    }
  }, [brief, generatedAt]);

  return { feed };
}
