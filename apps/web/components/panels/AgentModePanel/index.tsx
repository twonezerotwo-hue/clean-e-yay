"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useAgentModeConfig } from "@/lib/queries/hooks";
import { qk } from "@/lib/queries/keys";
import { api } from "@/lib/api/client";
import type { AgentModeConfigValues } from "@/types/generated/api";

// Faz 3 — Agent Mode Control (packages/mode/). Owner profil/strateji izinlerini
// buradan ayarlar; yazım file-backed override store'a gider (ana config'e
// dokunmaz). Frontend hesap YAPMAZ; tüm değerler /api/v1/agent-mode/config
// ViewModel'inden gelir. NOT: bu filtre şu an conflict_resolver/shadow
// gözleminde okunur — live auto-open'ı Faz 4'e kadar DEĞİŞTİRMEZ.

const STRATEGY_TOGGLES: Array<{ key: keyof AgentModeConfigValues; label: string }> = [
  { key: "allow_trend_follow_trades", label: "Trend-takip" },
  { key: "allow_reversal_trades", label: "Reversal" },
  { key: "allow_range_trades", label: "Range" },
  { key: "allow_breakout_trades", label: "Breakout" },
  { key: "allow_counter_context_trades", label: "Counter-context" },
];

function Pill({ on, label, onClick, busy }: { on: boolean; label: string; onClick: () => void; busy: boolean }) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      className={`rounded px-2 py-1 text-[11px] uppercase tracking-wide transition disabled:opacity-40 ${
        on
          ? "border border-signal-up/40 bg-signal-up/10 text-signal-up"
          : "border border-white/15 bg-white/[0.03] text-white/45"
      }`}
    >
      {label} · {on ? "ON" : "OFF"}
    </button>
  );
}

export function AgentModePanel() {
  const { data, isLoading } = useAgentModeConfig();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  if (isLoading) {
    return (
      <PanelFrame id="agent_mode">
        <PanelHeader title="İşlem Modu İzinleri" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const cfg = data?.config;
  const profiles = data?.trade_profiles ?? [];
  const disabled = new Set(cfg?.disabled_trade_profiles ?? []);
  const hasOverrides = !!data && Object.keys(data.overrides ?? {}).length > 0;

  // Mevcut etkin config'i payload'a indir (POST tam set gönderir → server merge'ler).
  const basePayload = (): Partial<AgentModeConfigValues> =>
    cfg
      ? {
          disabled_trade_profiles: [...(cfg.disabled_trade_profiles ?? [])],
          allow_counter_context_trades: cfg.allow_counter_context_trades,
          allow_reversal_trades: cfg.allow_reversal_trades,
          allow_trend_follow_trades: cfg.allow_trend_follow_trades,
          allow_range_trades: cfg.allow_range_trades,
          allow_breakout_trades: cfg.allow_breakout_trades,
        }
      : {};

  const send = async (mut: (p: Partial<AgentModeConfigValues>) => Partial<AgentModeConfigValues>) => {
    setBusy(true);
    try {
      await api.agentModeConfigUpdate(mut(basePayload()));
      await qc.invalidateQueries({ queryKey: qk.agentModeConfig });
    } finally {
      setBusy(false);
    }
  };

  const toggleProfile = (p: string) =>
    send((payload) => {
      const set = new Set(payload.disabled_trade_profiles ?? []);
      if (set.has(p)) set.delete(p);
      else set.add(p);
      return { ...payload, disabled_trade_profiles: [...set] };
    });

  const toggleStrategy = (key: keyof AgentModeConfigValues) =>
    send((payload) => ({ ...payload, [key]: !(payload[key] as boolean) }));

  const reset = async () => {
    setBusy(true);
    try {
      await api.agentModeConfigReset();
      await qc.invalidateQueries({ queryKey: qk.agentModeConfig });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelFrame id="agent_mode">
      <PanelHeader
        title="İşlem Modu İzinleri"
        subtitle="Hangi işlem türlerine izin var (sen belirlersin)"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
              hasOverrides ? "bg-amber-400/20 text-amber-300" : "bg-white/10 text-white/55"
            }`}
          >
            {hasOverrides ? "ÖZEL" : "VARSAYILAN"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        Bu izinler şu an conflict_resolver/shadow gözleminde okunur — live auto-open&apos;ı
        Faz 4&apos;e kadar değiştirmez. OFF yapılan profil/strateji yeni pipeline&apos;da bloklanır.
      </p>

      <div className="text-[10px] uppercase tracking-widest text-white/40">Trade profilleri</div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {profiles.map((p) => (
          <Pill
            key={p}
            label={p}
            on={!disabled.has(p)}
            busy={busy}
            onClick={() => toggleProfile(p)}
          />
        ))}
      </div>

      <div className="mt-3 text-[10px] uppercase tracking-widest text-white/40">Stratejiler</div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {STRATEGY_TOGGLES.map(({ key, label }) => (
          <Pill
            key={key}
            label={label}
            on={!!cfg?.[key]}
            busy={busy}
            onClick={() => toggleStrategy(key)}
          />
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between text-[10px] text-white/35">
        <span>{hasOverrides ? "Owner override aktif" : "Tümü serbest (varsayılan)"}</span>
        {hasOverrides ? (
          <button
            type="button"
            disabled={busy}
            onClick={reset}
            className="rounded border border-white/15 bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-white/60 hover:bg-white/10 disabled:opacity-40"
          >
            {busy ? "…" : "Sıfırla"}
          </button>
        ) : null}
      </div>
    </PanelFrame>
  );
}
