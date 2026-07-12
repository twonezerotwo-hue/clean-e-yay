"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCouncil } from "@/lib/queries/hooks";
import type { CouncilView } from "@/types/uncontracted";

// Konsey karnesi — katmanlar-arası kombinasyon analizi (owner 2026-07-12:
// "katmanlar birbirinden habersiz"). Hangi modülün sesi gerçek ayırıcı
// (güçlü-vs-zayıf isabet yayılımı), rejim/güven kırılımları ve VERİDEN
// türetilen sanki-filtreler ("şu kapı olsaydı ne olurdu"). Filtreler her
// koşuda yeniden keşfedilir — sabit kural gömülü değil. IN-SAMPLE kanıttır;
// karara bağlanacak filtre önce gölge + ileri-veri ister. Panel HESAP YAPMAZ.

function wrColor(v: number | null): string {
  if (v === null) return "text-white/50";
  return v >= 50 ? "text-signal-up/80" : v <= 40 ? "text-signal-down/80" : "text-white/60";
}

export function CouncilPanel() {
  const { data, isLoading } = useCouncil();

  if (isLoading) {
    return (
      <PanelFrame id="council">
        <PanelHeader title="Konsey Karnesi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: CouncilView | undefined = data;
  const spreads = d?.module_spreads ?? [];
  const whatIf = d?.what_if ?? [];

  return (
    <PanelFrame id="council">
      <PanelHeader
        title="Konsey Karnesi"
        subtitle="Katmanlar birlikte ne söylüyor — modül yayılımları + veriden türetilen sanki-filtreler"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            in-sample kanıt
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          <div className="mb-2 text-[11px] leading-4 text-white/55">
            {d.n} temiz işlem üzerinden (legacy hariç). Yayılım = modülün sesi
            güçlüyken vs zayıfken isabet farkı; artı büyükse o modül gerçek
            ayırıcı, eksiyse ters gösterge.
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">Modül</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Güçlü isabet</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Zayıf isabet</th>
                  <th className="py-0.5 text-right font-medium">Yayılım</th>
                </tr>
              </thead>
              <tbody>
                {spreads.map((s) => (
                  <tr key={s.module} className="border-t border-white/5">
                    <td className="py-0.5 pr-2 font-mono text-white/70">{s.module}</td>
                    <td className={`py-0.5 pr-2 text-right font-mono ${wrColor(s.strong.win_pct)}`}>
                      %{s.strong.win_pct} <span className="text-white/35">({s.strong.n})</span>
                    </td>
                    <td className={`py-0.5 pr-2 text-right font-mono ${wrColor(s.weak.win_pct)}`}>
                      %{s.weak.win_pct} <span className="text-white/35">({s.weak.n})</span>
                    </td>
                    <td
                      className={`py-0.5 text-right font-mono font-bold ${
                        s.win_spread > 0 ? "text-signal-up/80" : "text-signal-down/80"
                      }`}
                    >
                      {s.win_spread > 0 ? "+" : ""}
                      {s.win_spread}p
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mb-2 mt-3 border-t border-white/10 pt-2 text-[11px] font-bold text-white/70">
            Sanki-filtreler{" "}
            <span className="font-normal text-white/45">
              (veriden türetilir; kapı değildir — kanıttır)
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">Filtre</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Kalan işlem</th>
                  <th className="py-0.5 pr-2 text-right font-medium">İsabet</th>
                  <th className="py-0.5 text-right font-medium">PnL</th>
                </tr>
              </thead>
              <tbody>
                {whatIf.map((w) => (
                  <tr key={w.filter} className="border-t border-white/5">
                    <td className="py-0.5 pr-2 text-white/70">{w.filter}</td>
                    <td className="py-0.5 pr-2 text-right font-mono text-white/60">%{w.kept_pct}</td>
                    <td className={`py-0.5 pr-2 text-right font-mono ${wrColor(w.win_pct)}`}>
                      %{w.win_pct}
                    </td>
                    <td
                      className={`py-0.5 text-right font-mono ${
                        (w.total_pnl ?? 0) > 0 ? "text-signal-up/80" : "text-signal-down/80"
                      }`}
                    >
                      ${w.total_pnl}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            Salt-analiz — canlı karara dokunmaz. Filtreler aynı veriden türetilip
            aynı veride ölçülür (in-sample); karara bağlanacak filtre önce gölge +
            ileri-veri kanıtı ister.
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          {d?.status === "INSUFFICIENT"
            ? `Konsey konuşmak için daha çok temiz işlem bekliyor (${d.n}/${d.min_rows}).`
            : "Konsey karnesi henüz üretilmedi — öğrenme döngüsü (günlük) çalışınca burada görünecek."}
        </div>
      )}
    </PanelFrame>
  );
}
