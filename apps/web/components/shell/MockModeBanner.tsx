"use client";

import { useDataSnapshot } from "@/lib/queries/hooks";

/**
 * `PRICE_USE_MOCK=true` runtime opt-in açıkken üst kısımda kırmızı uyarı.
 * Politika: runtime'da mock yasak; bu mod sadece dev/diagnostic içindir.
 */
export function MockModeBanner() {
  const { data } = useDataSnapshot();
  if (!data?.mode.mock_warning) return null;
  return (
    <div className="rounded-lg border border-signal-down/40 bg-signal-down/10 px-4 py-2 text-xs uppercase tracking-widest text-signal-down flex items-center justify-between">
      <span>⚠ TEST/MOCK MODE — gerçek veri yerine mock kullanılıyor.</span>
      <span className="text-[10px] opacity-70">
        PRICE_USE_MOCK=true · production'da kullanmayın
      </span>
    </div>
  );
}
