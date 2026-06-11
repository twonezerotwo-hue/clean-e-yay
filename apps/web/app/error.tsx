"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[route-error]", error);
  }, [error]);
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4 p-6">
      <h1 className="text-xl font-medium">Bir şeyler ters gitti.</h1>
      <p className="text-sm text-white/60 max-w-prose text-center">
        Pano yüklenirken beklenmedik bir hata oluştu. Detaylar konsolda.
      </p>
      <button
        type="button"
        onClick={reset}
        className="rounded-md px-4 py-1.5 bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30 transition"
      >
        Tekrar dene
      </button>
    </main>
  );
}
