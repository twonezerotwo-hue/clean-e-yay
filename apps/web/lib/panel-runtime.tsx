"use client";

import { createContext, useContext, type ReactNode } from "react";

type PanelRuntime = {
  visible: boolean;
  mounted: boolean;
};

type PanelQueryPolicy = {
  refetchInterval: number | false;
  refetchIntervalInBackground: false;
  refetchOnReconnect: boolean;
  refetchOnWindowFocus: boolean;
};

const PanelRuntimeContext = createContext<PanelRuntime>({
  visible: true,
  mounted: true,
});

export function PanelRuntimeProvider({
  visible,
  mounted = true,
  children,
}: {
  visible: boolean;
  mounted?: boolean;
  children: ReactNode;
}) {
  return (
    <PanelRuntimeContext.Provider value={{ visible, mounted }}>
      {children}
    </PanelRuntimeContext.Provider>
  );
}

export function usePanelRuntime() {
  return useContext(PanelRuntimeContext);
}

export function usePanelQueryPolicy(refetchInterval?: number): PanelQueryPolicy {
  const { visible } = usePanelRuntime();
  return {
    refetchInterval:
      visible && refetchInterval != null ? refetchInterval : false,
    refetchIntervalInBackground: false,
    refetchOnReconnect: visible,
    refetchOnWindowFocus: visible,
  };
}
