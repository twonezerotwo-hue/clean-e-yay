"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { PanelRuntimeProvider } from "@/lib/panel-runtime";

export function LazyPanelMount({
  anchorId,
  children,
  minHeight = 220,
  rootMargin = "1100px 0px",
}: {
  anchorId?: string;
  children: ReactNode;
  minHeight?: number;
  rootMargin?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setMounted(true);
      setVisible(true);
      return;
    }

    const currentHash = window.location.hash.replace(/^#/, "");
    if (anchorId && currentHash === anchorId) {
      setMounted(true);
      setVisible(true);
      return;
    }

    const margin = Number.parseInt(rootMargin, 10) || 0;
    const measureNearViewport = () => {
      const rect = node.getBoundingClientRect();
      const isNear =
        rect.top < window.innerHeight + margin && rect.bottom > -margin;
      setVisible(isNear);
      if (isNear) setMounted(true);
    };

    const frame = window.requestAnimationFrame(measureNearViewport);
    const observer = new IntersectionObserver(
      ([entry]) => {
        const isVisible = entry.isIntersecting;
        setVisible(isVisible);
        if (isVisible) setMounted(true);
      },
      { rootMargin, threshold: 0.01 },
    );

    observer.observe(node);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [anchorId, rootMargin]);

  const style: CSSProperties = mounted
    ? {
        contentVisibility: "auto",
        containIntrinsicSize: `${minHeight}px`,
      }
    : { minHeight };

  return (
    <div
      ref={ref}
      id={mounted ? undefined : anchorId}
      data-lazy-panel={anchorId}
      style={style}
    >
      <PanelRuntimeProvider visible={visible} mounted={mounted}>
        {mounted ? (
          children
        ) : (
          <div className="min-h-[inherit] rounded-xl border border-white/8 bg-white/[0.025]" />
        )}
      </PanelRuntimeProvider>
    </div>
  );
}
