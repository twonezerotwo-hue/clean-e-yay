"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useRegimeReport } from "@/lib/queries/hooks";
import { selectTopAssets } from "@/lib/selectors/regime";
import type { AssetSignal, RegimeLayer } from "@/types/generated/api";

type FlowNode = {
  id: string;
  label: string;
  value: number;
  direction: "in" | "out" | "neutral";
  kind: "layer" | "asset";
};

const NODE_META: Record<string, { icon: string; tone: string }> = {
  BTCUSD: { icon: "BTC", tone: "border-orange-300/35 text-orange-200 bg-orange-300/10" },
  ETHUSD: { icon: "ETH", tone: "border-violet-300/35 text-violet-200 bg-violet-300/10" },
  XAUUSD: { icon: "Au", tone: "border-amber-300/35 text-amber-200 bg-amber-300/10" },
  XAGUSD: { icon: "Ag", tone: "border-slate-200/35 text-slate-100 bg-slate-200/10" },
};

function directionFromLayer(layer: RegimeLayer): FlowNode["direction"] {
  if (layer.direction === "bullish") return "in";
  if (layer.direction === "bearish") return "out";
  return "neutral";
}

function directionFromAsset(asset: AssetSignal): FlowNode["direction"] {
  if (asset.direction === "bullish") return "in";
  if (asset.direction === "bearish") return "out";
  return "neutral";
}

function flowTone(direction: FlowNode["direction"]) {
  if (direction === "in") return "border-emerald-400/45 text-emerald-200 bg-emerald-400/10";
  if (direction === "out") return "border-red-400/45 text-red-200 bg-red-400/10";
  return "border-amber-300/35 text-amber-200 bg-amber-300/10";
}

function flowLabel(direction: FlowNode["direction"]) {
  if (direction === "in") return "FLOW IN";
  if (direction === "out") return "FLOW OUT";
  return "NEUTRAL";
}

function NodeCard({ node }: { node: FlowNode }) {
  const meta = NODE_META[node.id] ?? { icon: node.id.slice(0, 3), tone: flowTone(node.direction) };
  return (
    <div className={`rounded-lg border px-3 py-2 ${flowTone(node.direction)} shadow-[0_0_22px_rgba(34,211,238,0.06)]`}>
      <div className="flex items-center gap-2">
        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border text-[10px] font-bold ${meta.tone}`}>
          {meta.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-white/82">{node.label}</div>
          <div className="text-[10px] uppercase tracking-widest text-white/36">{flowLabel(node.direction)}</div>
        </div>
        <div className="font-display text-lg tabular-nums text-white/88">{Math.round(node.value)}</div>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full ${node.direction === "out" ? "bg-red-300" : node.direction === "in" ? "bg-accent-cyan" : "bg-amber-300"}`}
          style={{ width: `${Math.max(6, Math.min(100, node.value))}%` }}
        />
      </div>
    </div>
  );
}

export function CapitalRotationPanel() {
  const { data } = useRegimeReport();
  const assets = selectTopAssets(data, 4);
  const layers = data?.layers ?? [];
  const layerNodes: FlowNode[] = layers.slice(0, 4).map((layer) => ({
    id: layer.name,
    label: layer.name,
    value: layer.score,
    direction: directionFromLayer(layer),
    kind: "layer",
  }));
  const assetNodes: FlowNode[] = assets.map((asset) => ({
    id: asset.symbol,
    label: asset.symbol,
    value: asset.score,
    direction: directionFromAsset(asset),
    kind: "asset",
  }));
  const nodes = [...layerNodes, ...assetNodes];
  const inCount = nodes.filter((node) => node.direction === "in").length;
  const outCount = nodes.filter((node) => node.direction === "out").length;
  const conviction = nodes.length
    ? Math.round(nodes.reduce((sum, node) => sum + node.value, 0) / nodes.length)
    : 0;
  const primary = inCount > outCount ? "risk-on flow" : outCount > inCount ? "risk-off flow" : "balanced flow";

  return (
    <PanelFrame id="capital_rotation" className="border-accent-cyan/20">
      <PanelHeader
        title="Sermaye Rotasyonu"
        subtitle="animated capital flow / layers + asset signals"
        actions={
          <span className="rounded border border-accent-cyan/25 bg-accent-cyan/10 px-2 py-1 text-[10px] uppercase tracking-widest text-accent-cyan">
            {primary}
          </span>
        }
      />
      {!nodes.length ? (
        <div className="text-xs italic text-white/40">veri yok</div>
      ) : (
        <div className="relative overflow-hidden rounded-lg border border-white/10 bg-[#04111f] p-3">
          <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(34,211,238,0.65)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.65)_1px,transparent_1px)] [background-size:46px_46px]" />
          <div className="relative grid gap-4 lg:grid-cols-[minmax(210px,0.7fr)_minmax(240px,0.6fr)_minmax(210px,0.7fr)]">
            <div className="space-y-2">
              {layerNodes.map((node) => (
                <NodeCard key={node.id} node={node} />
              ))}
            </div>

            <div className="relative flex min-h-[300px] items-center justify-center">
              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 260 320" aria-hidden>
                {nodes.map((node, index) => {
                  const left = index < layerNodes.length;
                  const y = 34 + (index % 4) * 68;
                  const stroke = node.direction === "out" ? "#f87171" : node.direction === "in" ? "#22d3ee" : "#fbbf24";
                  return (
                    <path
                      key={`${node.id}-${index}`}
                      d={left ? `M0 ${y} C76 ${y}, 82 160, 130 160` : `M260 ${y} C184 ${y}, 178 160, 130 160`}
                      fill="none"
                      stroke={stroke}
                      strokeDasharray="5 6"
                      strokeWidth={1 + Math.min(node.value, 100) / 50}
                      opacity="0.54"
                      className={node.direction === "out" ? "capital-flow-line-reverse" : "capital-flow-line"}
                    />
                  );
                })}
              </svg>

              <div className="capital-core relative grid h-48 w-48 place-items-center rounded-full border border-accent-cyan/25 bg-[radial-gradient(circle_at_35%_25%,rgba(125,211,252,0.78),rgba(37,99,235,0.55)_38%,rgba(3,12,28,0.94)_78%)] shadow-[0_0_58px_rgba(34,211,238,0.24)]">
                <div className="absolute inset-4 rounded-full border border-accent-cyan/18" />
                <div className="absolute inset-8 rounded-full border border-dashed border-accent-cyan/22" />
                <div className="text-center">
                  <div className="text-[10px] uppercase tracking-[0.3em] text-cyan-100">Capital</div>
                  <div className="text-[10px] uppercase tracking-[0.3em] text-cyan-100">Flow</div>
                  <div className="mt-2 text-3xl font-display text-white">{conviction}</div>
                  <div className="text-[10px] uppercase tracking-widest text-white/45">{data?.regime_label ?? "regime"}</div>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              {assetNodes.map((node) => (
                <NodeCard key={node.id} node={node} />
              ))}
            </div>
          </div>

          <div className="relative mt-3 grid gap-2 border-t border-white/10 pt-3 text-[11px] text-white/54 sm:grid-cols-3">
            <div>In-flow nodes: <span className="text-emerald-300">{inCount}</span></div>
            <div>Out-flow nodes: <span className="text-red-300">{outCount}</span></div>
            <div>Mode: <span className="text-accent-cyan">PAPER_SAFE / NO_EXECUTION</span></div>
          </div>
        </div>
      )}
    </PanelFrame>
  );
}
