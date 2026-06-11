"use client";

import { Component, type ReactNode } from "react";

/**
 * Tek, jenerik ErrorBoundary. Eski projede 6 kopya vardı (her panel için ayrı);
 * burada tek tanımla hepsi karşılanır.
 */
export class ErrorBoundary extends Component<
  { fallback: ReactNode; onError?: (err: Error) => void; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
