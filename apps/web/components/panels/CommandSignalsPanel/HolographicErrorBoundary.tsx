"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message?: string;
}

/**
 * Holographic katmanı render crash'inde sayfayı korur — boş bir hata
 * mesajı gösterir. Karar zincirine etkisi yok.
 */
export default class HolographicErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err?.message ?? "render_error" };
  }

  componentDidCatch(): void {
    // intentionally silent
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-2xl border border-amber-700/50 bg-amber-950/30 p-4">
          <p className="text-xs text-amber-200">
            Holografik görünüm yüklenemedi — yenilemek için sayfayı reload yapın.
          </p>
          {this.state.message ? (
            <p className="text-[10px] font-mono text-amber-300/70 mt-1">
              detay: {this.state.message}
            </p>
          ) : null}
        </div>
      );
    }
    return this.props.children;
  }
}
