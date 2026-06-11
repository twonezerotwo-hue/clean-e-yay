"use client";

import { useCallback, useEffect, useState } from "react";

import { PANEL_REGISTRY, type PanelKey } from "@/lib/panel-registry";

const STORAGE_KEY = "clean-eyay:panels-v1";

type VisibilityMap = Partial<Record<PanelKey, boolean>>;

const readStored = (): VisibilityMap => {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
};

const defaults = (): VisibilityMap => {
  const out: VisibilityMap = {};
  for (const p of PANEL_REGISTRY) out[p.id] = p.defaultVisible;
  return out;
};

export function usePanelVisibility() {
  const [state, setState] = useState<VisibilityMap>(defaults);

  useEffect(() => {
    setState({ ...defaults(), ...readStored() });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const toggle = useCallback((id: PanelKey) => {
    setState((s) => ({ ...s, [id]: !s[id] }));
  }, []);

  const set = useCallback((id: PanelKey, value: boolean) => {
    setState((s) => ({ ...s, [id]: value }));
  }, []);

  return { visible: state, toggle, set };
}
