"use client";

import { useEffect } from "react";

import { useRealtimeRefresh } from "./useRealtimeRefresh";

/**
 * Cmd/Ctrl + R: manual refresh (browser refresh'ini ezer)
 */
export function useKeyboardShortcuts() {
  const refresh = useRealtimeRefresh();
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        refresh();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [refresh]);
}
