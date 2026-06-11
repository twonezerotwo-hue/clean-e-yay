"""G4 — Correlation-aware sizing.

Aynı yöne yüksek korelasyonlu pozisyonların toplam exposure'unu sınırlar.

Politika:
- **RiskGate'i bypass etmez** — KILL_SWITCH / RISK_REDUCE /
  NO_POSITION_INCREASE her zaman önce çalışır; bu modül yalnızca consensus +
  mistake gate'i geçen adayların boyutunu küçültür. **Asla artırmaz**
  (size_factor ≤ 1.0).
- |rho| ≥ `correlation_threshold` (0.7) → aynı risk cluster.
  İşaretli hizalama = rho × side_sign(pozisyon) × side_sign(aday):
  hizalama ≥ +threshold → cluster üyesi (exposure'a eklenir);
  hizalama ≤ -threshold → hedge (ayrı raporlanır, cap'e girmez).
- Cluster toplamı ≥ `max_cluster_pct` (0.30 equity) → size_factor 0.0;
  yarısını aştıysa → 0.5.
- rho kaynağı: yeterli veri varsa kapalı trade PnL serisinden hesaplanır
  (computed); yetersizse config `correlation_baseline` (baseline); o da
  yoksa neutral (rho=0, `insufficient_correlation_data` uyarısı, adjustment
  yok). DATA_POLICY: yalnızca `data_verified=True` trade'ler kullanılır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from packages.data.registry.loader import load_thresholds

SIDE_SIGN = {"long": 1.0, "short": -1.0}
REDUCE_FACTOR = 0.5


@dataclass
class CorrelationEntry:
    symbol_a: str
    symbol_b: str
    rho: float
    source: str          # computed | baseline | neutral
    samples: int         # computed için ortak gün sayısı, diğerlerinde 0


@dataclass
class ClusterMember:
    position_id: str
    symbol: str
    side: str
    size_usd: float
    rho: float
    source: str


@dataclass
class ClusterReport:
    candidate_symbol: str
    candidate_side: str
    threshold: float
    max_cluster_pct: float
    cluster_pct: float
    size_factor: float          # 0.0–1.0; asla 1.0'ın üstüne çıkmaz
    status: str                 # OK | REDUCED | CAPPED
    members: list[ClusterMember] = field(default_factory=list)
    hedges: list[ClusterMember] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _gates() -> dict:
    return load_thresholds()["risk_gates"]


def _baseline_rho(a: str, b: str) -> float | None:
    base = load_thresholds().get("correlation_baseline") or {}
    v = (base.get(a) or {}).get(b)
    if v is None:
        v = (base.get(b) or {}).get(a)
    return float(v) if v is not None else None


def _parse_day(ts: str | None) -> date | None:
    if not ts or len(ts) < 10:
        return None
    try:
        return date.fromisoformat(ts[:10])
    except ValueError:
        return None


def daily_pnl_series(trades, window_days: int | None = None) -> dict[str, dict[date, float]]:
    """Sembol → gün → toplam PnL. Sadece verified trade'ler (DATA_POLICY).

    Pencere, saat yerine veri setindeki en son kapanış gününe göre alınır —
    deterministik (replay/test güvenli).
    """
    if window_days is None:
        window_days = int(_gates().get("correlation_window_days", 30))
    days: list[tuple[str, date, float]] = []
    for t in trades:
        if not getattr(t, "data_verified", False):
            continue
        d = _parse_day(getattr(t, "closed_at", None))
        if d is None:
            continue
        days.append((t.symbol, d, float(t.pnl_usd)))
    if not days:
        return {}
    anchor = max(d for _, d, _ in days)
    cutoff = anchor - timedelta(days=window_days)
    out: dict[str, dict[date, float]] = {}
    for sym, d, pnl in days:
        if d < cutoff:
            continue
        out.setdefault(sym, {})
        out[sym][d] = out[sym].get(d, 0.0) + pnl
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def pair_correlation(
    a: str,
    b: str,
    series: dict[str, dict[date, float]],
) -> CorrelationEntry:
    """Tek çift için rho: computed → baseline → neutral fallback sırası."""
    if a == b:
        return CorrelationEntry(symbol_a=a, symbol_b=b, rho=1.0, source="computed", samples=0)
    min_overlap = int(_gates().get("correlation_min_overlap_days", 5))
    sa, sb = series.get(a, {}), series.get(b, {})
    common = sorted(set(sa) & set(sb))
    if len(common) >= min_overlap:
        rho = _pearson([sa[d] for d in common], [sb[d] for d in common])
        if rho is not None:
            return CorrelationEntry(
                symbol_a=a, symbol_b=b, rho=round(rho, 3),
                source="computed", samples=len(common),
            )
    base = _baseline_rho(a, b)
    if base is not None:
        return CorrelationEntry(symbol_a=a, symbol_b=b, rho=base, source="baseline", samples=0)
    return CorrelationEntry(symbol_a=a, symbol_b=b, rho=0.0, source="neutral", samples=0)


def matrix(symbols: list[str], trades=None) -> list[CorrelationEntry]:
    """Benzersiz çiftler için korelasyon matrisi girdileri."""
    if trades is None:
        from packages.paper import state as paper_state
        trades = paper_state.load().recent_trades
    series = daily_pnl_series(trades)
    syms = sorted(set(symbols))
    out: list[CorrelationEntry] = []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            out.append(pair_correlation(a, b, series))
    return out


def _lookup(entries: list[CorrelationEntry], a: str, b: str) -> CorrelationEntry | None:
    for e in entries:
        if {e.symbol_a, e.symbol_b} == {a, b}:
            return e
    return None


def cluster_exposure(
    open_positions,
    candidate_symbol: str,
    candidate_side: str,
    equity_usd: float,
    entries: list[CorrelationEntry] | None = None,
) -> ClusterReport:
    """Aday açılışın risk cluster exposure raporu.

    Sadece risk azaltıcı: size_factor ∈ {1.0, REDUCE_FACTOR, 0.0}.
    """
    gates = _gates()
    threshold = float(gates.get("correlation_threshold", 0.7))
    cap = float(gates.get("max_cluster_pct", 0.30))
    if entries is None:
        symbols = sorted({candidate_symbol, *(p.symbol for p in open_positions)})
        entries = matrix(symbols)

    members: list[ClusterMember] = []
    hedges: list[ClusterMember] = []
    warnings: list[str] = []
    cand_sign = SIDE_SIGN.get(candidate_side, 1.0)

    for p in open_positions:
        if p.symbol == candidate_symbol:
            rho, source = 1.0, "computed"
        else:
            e = _lookup(entries, p.symbol, candidate_symbol)
            if e is None or e.source == "neutral":
                pair = "|".join(sorted([p.symbol, candidate_symbol]))
                warnings.append(f"insufficient_correlation_data:{pair}")
                continue  # neutral fallback — adjustment uygulanmaz
            rho, source = e.rho, e.source
        alignment = rho * SIDE_SIGN.get(p.side, 1.0) * cand_sign
        member = ClusterMember(
            position_id=p.id,
            symbol=p.symbol,
            side=p.side,
            size_usd=float(p.size_usd),
            rho=rho,
            source=source,
        )
        if alignment >= threshold:
            members.append(member)
        elif alignment <= -threshold:
            hedges.append(member)

    cluster_pct = (
        round(sum(m.size_usd for m in members) / equity_usd, 4) if equity_usd > 0 else 0.0
    )
    if not members:
        size_factor, status = 1.0, "OK"
    elif cluster_pct >= cap:
        size_factor, status = 0.0, "CAPPED"
        warnings.append(f"correlation_cluster_cap:{cluster_pct:.0%} ≥ {cap:.0%}")
    elif cluster_pct >= cap * 0.5:
        size_factor, status = REDUCE_FACTOR, "REDUCED"
    else:
        size_factor, status = 1.0, "OK"

    return ClusterReport(
        candidate_symbol=candidate_symbol,
        candidate_side=candidate_side,
        threshold=threshold,
        max_cluster_pct=cap,
        cluster_pct=cluster_pct,
        size_factor=size_factor,
        status=status,
        members=members,
        hedges=hedges,
        warnings=warnings,
    )


def open_clusters(
    open_positions,
    equity_usd: float,
    entries: list[CorrelationEntry] | None = None,
) -> list[dict]:
    """Açık pozisyonları aynı-yönlü risk cluster'larına grupla (endpoint için).

    İki pozisyon, işaretli hizalama (rho × side_sign × side_sign) ≥ threshold
    ise aynı cluster'dadır (bağlantılı bileşenler).
    """
    gates = _gates()
    threshold = float(gates.get("correlation_threshold", 0.7))
    cap = float(gates.get("max_cluster_pct", 0.30))
    positions = list(open_positions)
    if entries is None:
        symbols = sorted({p.symbol for p in positions})
        entries = matrix(symbols)

    parent = list(range(len(positions)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i, a in enumerate(positions):
        for j in range(i + 1, len(positions)):
            b = positions[j]
            if a.symbol == b.symbol:
                rho = 1.0
            else:
                e = _lookup(entries, a.symbol, b.symbol)
                if e is None or e.source == "neutral":
                    continue
                rho = e.rho
            alignment = rho * SIDE_SIGN.get(a.side, 1.0) * SIDE_SIGN.get(b.side, 1.0)
            if alignment >= threshold:
                union(i, j)

    groups: dict[int, list] = {}
    for i, p in enumerate(positions):
        groups.setdefault(find(i), []).append(p)

    out: list[dict] = []
    for grp in groups.values():
        total = sum(float(p.size_usd) for p in grp)
        pct = round(total / equity_usd, 4) if equity_usd > 0 else 0.0
        if pct >= cap:
            status = "BREACH"
        elif pct >= cap * 0.5:
            status = "WARNING"
        else:
            status = "OK"
        out.append(
            {
                "symbols": sorted({p.symbol for p in grp}),
                "positions": [
                    {"id": p.id, "symbol": p.symbol, "side": p.side, "size_usd": float(p.size_usd)}
                    for p in grp
                ],
                "total_usd": round(total, 2),
                "cluster_pct": pct,
                "status": status,
            }
        )
    out.sort(key=lambda c: -c["cluster_pct"])
    return out
