"use client";

import { useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";

type MobileFlipCardProps = {
  front: ReactNode;
  back: ReactNode;
  title?: string;
  defaultSide?: "front" | "back";
  className?: string;
};

function shouldIgnoreToggle(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    Boolean(
      target.closest(
        "a, button, input, textarea, select, summary, details, [contenteditable='true'], [data-no-flip]",
      ),
    )
  );
}

export function MobileFlipCard({
  front,
  back,
  title,
  defaultSide = "front",
  className = "",
}: MobileFlipCardProps) {
  const [side, setSide] = useState(defaultSide);
  const isBack = side === "back";
  const toggle = () => setSide((current) => (current === "front" ? "back" : "front"));

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    if (shouldIgnoreToggle(event.target)) return;
    toggle();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (shouldIgnoreToggle(event.target)) return;
    event.preventDefault();
    toggle();
  };

  return (
    <section
      className={`mobile-flip-card ${isBack ? "is-back" : ""} ${className}`}
      data-side={side}
      role="button"
      tabIndex={0}
      aria-label={title}
      aria-expanded={isBack}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <div className="mobile-flip-card__inner">
        <div className="mobile-flip-card__face mobile-flip-card__front">
          {front}
        </div>
        <div className="mobile-flip-card__face mobile-flip-card__back">
          {back}
        </div>
      </div>
      <button
        type="button"
        className="mobile-flip-card__toggle"
        aria-pressed={isBack}
        onClick={(event) => {
          event.stopPropagation();
          toggle();
        }}
      >
        {isBack ? "Özet" : "Detay"}
      </button>
    </section>
  );
}
