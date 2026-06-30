"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useGuardSafety, useGuardSafetyAdopt } from "@/lib/queries/hooks";
import type { GuardSafetyGuard, GuardSafetyView } from "@/types/generated/api";

// CP3 — yön güvenlik kasası paneli. Bağlı yön guard'ları (chop / exhaustion /
// reversion / self_conflict) için engine'in gördüğü EFEKTİF durum + canlı izleme
// ilerlemesi. Kasa bir guard'ı canlıda izlerken expectancy baseline'ın altına
// düşerse oto-kapatır. Frontend hesap YAPMAZ; her şey /learning/guard-safety'den.

function StateChip({ g }: { g: GuardSafetyGuard }) {
  if (g.vault_disabled) {
    return (
      <span className="rounded bg-signal-down/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-signal-down">
        Kasa kapattı
      </span>
    );
  }
  if (g.monitoring) {
    const adopted = g.monitor?.mode === "adopted";
    return (
      <span
        className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-300"
        title={adopted ? "Sürüklenme alarmı (yalnız öneri)" : "Kanıtlı izleme (oto-kapat)"}
      >
        {adopted ? "İzleniyor (öneri)" : "İzleniyor"}
      </span>
    );
  }
  if (g.effective_enabled) {
    return (
      <span className="rounded bg-signal-up/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-signal-up">
        Canlı
      </span>
    );
  }
  return (
    <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/50">
      Kapalı
    </span>
  );
}

function GuardRow({ g }: { g: GuardSafetyGuard }) {
  const m = g.monitor;
  return (
    <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-white/80">{g.label}</span>
        <StateChip g={g} />
      </div>
      {m ? (
        <div className="mt-1 flex justify-between text-[10px] text-white/45">
          <span>
            Baseline:{" "}
            <span className="tabular-nums text-white/70">{m.baseline_expectancy}</span>
          </span>
          <span>
            Canlı:{" "}
            <span
              className={`tabular-nums ${
                m.post_n >= m.need
                  ? m.post_expectancy < m.baseline_expectancy
                    ? "text-signal-down"
                    : "text-signal-up"
                  : "text-white/70"
              }`}
            >
              {m.post_expectancy}
            </span>
          </span>
          <span>
            Örnek:{" "}
            <span className="tabular-nums text-white/70">
              {m.post_n}/{m.need}
            </span>
          </span>
        </div>
      ) : g.vault_disabled && g.override?.reason ? (
        <div className="mt-1 truncate text-[10px] text-white/45" title={g.override.reason}>
          {g.override.reason}
        </div>
      ) : null}
    </div>
  );
}

export function GuardSafetyPanel() {
  const { data, isLoading } = useGuardSafety();
  const adopt = useGuardSafetyAdopt();

  if (isLoading) {
    return (
      <PanelFrame id="guard_safety">
        <PanelHeader title="Koruma Filtresi Güvenliği" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: GuardSafetyView | undefined = data;
  const guards = d?.guards ?? [];
  const autoOn = d?.auto_disable_enabled ?? false;
  // Canlı ama izlenmeyen + kasa-kapatmamış guard'lar adopte edilebilir.
  const adoptable = guards.filter(
    (g) => g.effective_enabled && !g.monitoring && !g.vault_disabled,
  );

  return (
    <PanelFrame id="guard_safety">
      <PanelHeader
        title="Koruma Filtresi Güvenliği"
        subtitle="Açık koruma filtreleri işe yarıyor mu; zarar verirse kapatır"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              autoOn ? "bg-signal-up/20 text-signal-up" : "bg-white/10 text-white/55"
            }`}
          >
            {autoOn ? "Oto-kapat AÇIK" : "Yalnız öneri"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Owner bir yön guard'ını canlıya aldığında kasa onu izler. Yeterli yeni işlem
        sonrası beklenti enable öncesi <strong className="text-white/75">baseline</strong>'ın
        {" "}altına düşerse guard'ı geri alır (config'e dokunmadan).
      </p>

      {adoptable.length ? (
        <button
          type="button"
          onClick={() => adopt.mutate()}
          disabled={adopt.isPending}
          className="mb-2 w-full rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[11px] font-medium text-amber-200 transition hover:bg-amber-400/20 disabled:opacity-50"
          title="Zaten açık guard'ları sürüklenme alarmı olarak izlemeye al (yalnız öneri)"
        >
          {adopt.isPending
            ? "İzlemeye alınıyor…"
            : `${adoptable.length} canlı guard'ı izlemeye al (öneri modu)`}
        </button>
      ) : null}

      {guards.length ? (
        <div className="flex flex-col gap-1.5">
          {guards.map((g) => (
            <GuardRow key={g.guard_key} g={g} />
          ))}
        </div>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Bağlı yön guard'ı yok.
        </div>
      )}
    </PanelFrame>
  );
}
