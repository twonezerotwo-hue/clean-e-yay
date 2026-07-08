"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useZeroTwoStrategy } from "@/lib/queries/hooks";
import type { ZeroTwoStrategyCell, ZeroTwoStrategyView } from "@/types/uncontracted";

// Owner'ın 0-2 tam-akışı (0.618 giriş + fib hedef + 0-2 trailing + sabit-bahis
// house-money re-giriş) gölge karnesi. Her hücre TF×pivot: işlem, isabet, ilk-işlem
// PnL, house-money'li PnL. Canlı karara DOKUNMAZ; /learning/zero-two-strategy.
// Panel HESAP YAPMAZ. Sayılar flat-veri + örtüşen işlemle şişebilir → ileri-veri şart.

function rColor(v: number): string {
  return v > 0 ? "text-signal-up/80" : v < 0 ? "text-signal-down/80" : "text-white/50";
}

function fmtR(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`;
}

function CellRow({ c }: { c: ZeroTwoStrategyCell }) {
  const [tf, right, grp] = c.label.split("|");
  return (
    <tr className="border-t border-white/5">
      <td className="py-0.5 pr-2 font-mono text-white/70">
        {tf} <span className="text-white/35">{right}</span>
        {c.real_wick ? (
          <span className="ml-1 rounded bg-signal-up/15 px-1 text-[8px] text-signal-up/80">
            gerçek
          </span>
        ) : (
          <span className="ml-1 rounded bg-white/5 px-1 text-[8px] text-white/35">flat</span>
        )}
      </td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/50">{grp}</td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{c.n}</td>
      <td className="py-0.5 pr-2 text-right font-mono text-white/60">%{Math.round(c.win_pct)}</td>
      <td className={`py-0.5 pr-2 text-right font-mono ${rColor(c.ilk_total_r)}`}>{fmtR(c.ilk_total_r)}</td>
      <td className={`py-0.5 pr-2 text-right font-mono font-bold ${rColor(c.hm_total_r)}`}>
        {fmtR(c.hm_total_r)}
      </td>
      <td className="py-0.5 text-right font-mono text-white/45">
        {c.reentry_win}/{c.reentry_n}
      </td>
    </tr>
  );
}

export function ZeroTwoStrategyPanel() {
  const { data, isLoading } = useZeroTwoStrategy();

  if (isLoading) {
    return (
      <PanelFrame id="zero_two_strategy">
        <PanelHeader title="0-2 Strateji (House-Money)" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: ZeroTwoStrategyView | undefined = data;
  const cells = d?.cells ?? [];
  // En güvenilir hücre: gerçek fitilli + en çok işlem.
  const trusted = [...cells].filter((c) => c.real_wick).sort((a, b) => b.n - a.n)[0];

  return (
    <PanelFrame id="zero_two_strategy">
      <PanelHeader
        title="0-2 Strateji (House-Money)"
        subtitle="Owner 0-2 tam-akışı: giriş + fib hedef + trailing + sabit-bahis re-giriş"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            gölge
          </span>
        }
      />

      {d && d.status === "OK" && cells.length ? (
        <>
          {trusted ? (
            <div className="mb-2 rounded border border-signal-up/25 bg-signal-up/[0.06] px-2 py-1.5 text-[11px] leading-4 text-white/80">
              <span className="font-bold text-signal-up/90">En güvenilir (gerçek fitilli):</span>{" "}
              {trusted.tf} · {trusted.n} işlem · isabet %{Math.round(trusted.win_pct)} ·{" "}
              ilk <b className={rColor(trusted.ilk_total_r)}>{fmtR(trusted.ilk_total_r)}</b> →{" "}
              +house-money <b className={rColor(trusted.hm_total_r)}>{fmtR(trusted.hm_total_r)}</b>
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">TF · pivot</th>
                  <th className="py-0.5 pr-2 text-right font-medium">grup</th>
                  <th className="py-0.5 pr-2 text-right font-medium">işlem</th>
                  <th className="py-0.5 pr-2 text-right font-medium">isabet</th>
                  <th className="py-0.5 pr-2 text-right font-medium">ilk PnL</th>
                  <th className="py-0.5 pr-2 text-right font-medium">+house</th>
                  <th className="py-0.5 text-right font-medium">re-giriş</th>
                </tr>
              </thead>
              <tbody>
                {cells.map((c) => (
                  <CellRow key={c.label} c={c} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            Gölge — canlı skora/karara dokunmaz. &quot;gerçek&quot; = gerçek fitilli
            veri (güvenilir); &quot;flat&quot; hücreler + örtüşen işlemler PnL&apos;i
            şişirir. Kanıt ileri-veriyle olgunlaşınca owner onayıyla değerlendirilir.
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Karne henüz üretilmedi. Öğrenme döngüsü (haftalık) çalışınca 0-2
          stratejisi + house-money sonuçları burada görünecek.
        </div>
      )}
    </PanelFrame>
  );
}
