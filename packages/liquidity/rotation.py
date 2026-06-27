"""Küresel Likidite Rotasyon — sabit sepet için flow skoru (1D / 7D / 30D).

Veri kaynağı: YALNIZCA OHLCV cache (close + volume, verified) + (BTC/ETH için)
DefiLlama zincir TVL geçmişi. Karar VERMEZ; saf gözlemci. "Nakit nereye akıyor?"
sorusunu fiyat momentumu + hacim teyidi + makro uyum (DXY/VIX) + TVL değişimi
(gerçek para akışı, zincire kilitlenen/çekilen TVL) − volatilite cezasından
dolaylı okur.

ETF / fon-akışı (GLD/SPY/BTC-ETF inflow, stablecoin, repo) hâlâ YOK (ücretsiz/
güvenilir kaynak bulunamadı — DATA_POLICY: tahmini/mock veri eklenmez). TVL,
yalnızca kripto zinciri olan BTCUSD/ETHUSD için kullanılabilir; diğer asset'lerde
o bileşenin ağırlığı kalan bileşenlere orantılı redistribute edilir.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from packages.data.providers.liquidity import defillama
from packages.data.providers.ohlcv import cache
from packages.data.registry import assets as _asset_registry


def _basket() -> list[tuple[str, str, str]]:
    """(symbol, label, kind) — config/assets.yaml'daki 'liquidity' rollü varlıklar.
    Sepete ekle/çıkar = assets.yaml'ı düzenle."""
    return _asset_registry.liquidity_basket()

WINDOWS: dict[str, int] = {"1D": 1, "7D": 7, "30D": 30}

# Flow skoru ağırlıkları — TVL verisi olan asset'te (BTC/ETH) 5 bileşen, yoksa
# W_TVL diğer 4'e orantılı redistribute edilir (toplam ağırlık her durumda 1.0'a
# normalize edilir, bkz. _asset_flow).
W_MOMENTUM = 0.40
W_VOLUME = 0.22
W_MACRO = 0.18
W_VOLPEN = 0.08
W_TVL = 0.12

# Sembol → DefiLlama zincir adı (yalnızca gerçek on-chain TVL'si olan varlıklar).
_TVL_CHAIN: dict[str, str] = {"BTCUSD": "bitcoin", "ETHUSD": "ethereum"}


def _logistic(x: float, k: float = 1.0) -> float:
    """x → (0,100). k eğim."""
    return 100.0 / (1.0 + math.exp(-k * x))


def _series(symbol: str) -> tuple[list[float], list[float]] | None:
    cb = cache.load(symbol, "1d")
    if not cb or len(cb.bars) < 2:
        return None
    closes = [float(b.close) for b in cb.bars if b.close is not None]
    vols = [float(b.volume or 0.0) for b in cb.bars]
    if len(closes) < 2:
        return None
    return closes, vols


def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-1 - n] == 0:
        return None
    return (closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100.0


def _window_return_history(closes: list[float], n: int, lookback: int = 120) -> list[float]:
    """Geçmiş n-günlük getiriler (momentum z-score için referans dağılım)."""
    out: list[float] = []
    start = max(n, len(closes) - lookback)
    for i in range(start, len(closes)):
        base = closes[i - n]
        if base:
            out.append((closes[i] - base) / base * 100.0)
    return out


def _zscore(value: float, sample: list[float]) -> float:
    if len(sample) < 5:
        return 0.0
    mean = sum(sample) / len(sample)
    var = sum((s - mean) ** 2 for s in sample) / len(sample)
    std = math.sqrt(var) or 1.0
    return (value - mean) / std


def _volume_score(vols: list[float], n: int) -> float:
    """Son n-gün ort. hacim / trailing 30g ort. → 0-100."""
    if len(vols) < 31:
        return 50.0
    recent = vols[-n:] if n <= len(vols) else vols
    base = vols[-31:-1]
    recent_avg = sum(recent) / len(recent) if recent else 0.0
    base_avg = sum(base) / len(base) if base else 0.0
    if base_avg <= 0:
        return 50.0
    ratio = recent_avg / base_avg
    return _logistic((ratio - 1.0), k=2.5)


def _realized_vol_pct(closes: list[float], n: int = 20) -> float:
    """Son n-günün getiri std'i, geçmiş dağılımdaki yüzdelik → 0-100 (yüksek=riskli)."""
    if len(closes) < n + 30:
        return 50.0
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100.0
        for i in range(1, len(closes))
        if closes[i - 1]
    ]
    if len(rets) < n + 10:
        return 50.0
    window = rets[-n:]
    mean = sum(window) / len(window)
    cur_vol = math.sqrt(sum((r - mean) ** 2 for r in window) / len(window))
    # geçmiş rolling vol dağılımı
    hist: list[float] = []
    for i in range(n, len(rets)):
        w = rets[i - n:i]
        m = sum(w) / len(w)
        hist.append(math.sqrt(sum((r - m) ** 2 for r in w) / len(w)))
    if not hist:
        return 50.0
    below = sum(1 for h in hist if h <= cur_vol)
    return below / len(hist) * 100.0


def _tvl_change_pct(symbol: str, n: int) -> float | None:
    """Zincirin son n-gün TVL değişimi (%) — gerçek para akışı (fiyat değil).
    Yalnızca BTCUSD/ETHUSD (gerçek on-chain zincir) için; veri yoksa None
    (mock üretilmez, ağırlık diğer bileşenlere redistribute edilir)."""
    chain = _TVL_CHAIN.get(symbol)
    if chain is None:
        return None
    history = defillama.get_chain_tvl_history(chain)
    if not history or len(history) <= n:
        return None
    tvls = [tvl for _ts, tvl in history]
    base = tvls[-1 - n]
    if not base:
        return None
    return (tvls[-1] - base) / base * 100.0


def _tvl_score(symbol: str, n: int) -> float | None:
    """TVL değişimi → 0-100 (artış = zincire para giriyor, azalış = çıkıyor)."""
    chg = _tvl_change_pct(symbol, n)
    if chg is None:
        return None
    return _logistic(chg, k=0.8)


@dataclass
class _Macro:
    dxy_ret: float
    vix_ret: float

    @property
    def risk_tilt(self) -> float:
        """DXY ve VIX ikisi de düşüyorsa risk-on (+2), ikisi de yükseliyorsa (−2)."""
        tilt = 0.0
        tilt += -1.0 if self.dxy_ret < 0 else 1.0 if self.dxy_ret > 0 else 0.0
        tilt += -1.0 if self.vix_ret < 0 else 1.0 if self.vix_ret > 0 else 0.0
        return -tilt  # düşüş → pozitif risk-on


Series = dict[str, tuple[list[float], list[float]]]


def _macro_for_window(n: int, series: Series) -> _Macro:
    dxy = series.get("DXY")
    vix = series.get("VIX")
    dxy_ret = _ret(dxy[0], n) if dxy else None
    vix_ret = _ret(vix[0], n) if vix else None
    return _Macro(dxy_ret=dxy_ret or 0.0, vix_ret=vix_ret or 0.0)


def _macro_score(kind: str, macro: _Macro) -> float:
    """Varlık sınıfının makro rejimle uyumu → 0-100 (50 nötr)."""
    tilt = macro.risk_tilt  # +risk-on .. −risk-off  (≈ −2..+2)
    if kind in ("risk", "commodity"):
        return max(0.0, min(100.0, 50.0 + tilt * 12.0))
    if kind in ("safe", "cash"):
        return max(0.0, min(100.0, 50.0 - tilt * 12.0))
    if kind == "hedge":
        # hedge: VIX yükselişi (korku) + dolar güçsüzlüğü destekler
        s = 50.0
        s += 10.0 if macro.vix_ret > 0 else -6.0
        s += 6.0 if macro.dxy_ret < 0 else -4.0
        return max(0.0, min(100.0, s))
    return 50.0


@dataclass
class AssetFlow:
    symbol: str
    label: str
    kind: str
    ret: float | None
    volume_change_pct: float | None
    flow_score: float
    direction: str  # "in" | "out" | "neutral"
    tvl_change_pct: float | None = None


@dataclass
class WindowFlow:
    window: str
    assets: list[AssetFlow]
    regime: str
    regime_reasons: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)


def _direction(score: float) -> str:
    if score >= 60.0:
        return "in"
    if score <= 40.0:
        return "out"
    return "neutral"


def _asset_flow(
    symbol: str, label: str, kind: str, n: int, macro: _Macro, series: Series
) -> AssetFlow | None:
    s = series.get(symbol)
    if s is None:
        return None
    closes, vols = s
    ret = _ret(closes, n)
    if ret is None:
        return None
    # momentum: pencere getirisinin geçmiş dağılımdaki z-skoru → 0-100
    z = _zscore(ret, _window_return_history(closes, n))
    momentum = _logistic(z, k=1.0)
    volume = _volume_score(vols, n)
    macro_s = _macro_score(kind, macro)
    volpen = _realized_vol_pct(closes)
    tvl_chg = _tvl_change_pct(symbol, n)
    tvl_s = _tvl_score(symbol, n)
    # TVL yoksa (yalnız BTC/ETH'de var) W_TVL kalan bileşenlere orantılı
    # redistribute edilir — toplam ağırlık her durumda 1.0'a normalize olur.
    components: list[tuple[float, float]] = [
        (W_MOMENTUM, momentum),
        (W_VOLUME, volume),
        (W_MACRO, macro_s),
        (W_VOLPEN, 100.0 - volpen),
    ]
    if tvl_s is not None:
        components.append((W_TVL, tvl_s))
    total_w = sum(w for w, _ in components)
    flow = sum(w * v for w, v in components) / total_w
    flow = max(0.0, min(100.0, flow))
    # hacim değişimi (son n-gün ort / 30g ort − 1) yüzde
    vol_change = None
    if len(vols) >= 31:
        recent = vols[-n:] if n <= len(vols) else vols
        base = vols[-31:-1]
        ra = sum(recent) / len(recent) if recent else 0.0
        ba = sum(base) / len(base) if base else 0.0
        if ba > 0:
            vol_change = (ra / ba - 1.0) * 100.0
    return AssetFlow(
        symbol=symbol,
        label=label,
        kind=kind,
        ret=round(ret, 2),
        volume_change_pct=round(vol_change, 1) if vol_change is not None else None,
        flow_score=round(flow, 1),
        direction=_direction(flow),
        tvl_change_pct=round(tvl_chg, 2) if tvl_chg is not None else None,
    )


def _regime(assets: list[AssetFlow], macro: _Macro) -> tuple[str, list[str]]:
    by = {a.symbol: a for a in assets}
    risk = [by[s].flow_score for s in ("BTCUSD", "SP500") if s in by]
    safe = [by[s].flow_score for s in ("TLT", "DXY", "XAUUSD") if s in by]
    if not risk or not safe:
        return "NEUTRAL", []
    strength = (sum(risk) / len(risk)) - (sum(safe) / len(safe))
    if strength > 15:
        label = "RISK_ON"
    elif strength > 5:
        label = "CONTROLLED_RISK_ON"
    elif strength < -15:
        label = "CRISIS"
    elif strength < -5:
        label = "RISK_OFF"
    else:
        label = "NEUTRAL"
    reasons: list[str] = []
    reasons.append(f"DXY {'düşüyor' if macro.dxy_ret < 0 else 'yükseliyor' if macro.dxy_ret > 0 else 'yatay'}")
    reasons.append(f"VIX {'düşüyor' if macro.vix_ret < 0 else 'yükseliyor' if macro.vix_ret > 0 else 'yatay'}")
    if "BTCUSD" in by:
        reasons.append(f"BTC {by['BTCUSD'].direction}")
    if "SP500" in by:
        reasons.append(f"Hisse {by['SP500'].direction}")
    if "TLT" in by:
        reasons.append(f"Tahvil {by['TLT'].direction}")
    return label, reasons


def _contradictions(assets: list[AssetFlow]) -> list[str]:
    by = {a.symbol: a for a in assets}
    out: list[str] = []
    gold_in = by.get("XAUUSD") and by["XAUUSD"].direction == "in"
    btc_in = by.get("BTCUSD") and by["BTCUSD"].direction == "in"
    stocks_in = by.get("SP500") and by["SP500"].direction == "in"
    dxy_in = by.get("DXY") and by["DXY"].direction == "in"
    if gold_in and btc_in and stocks_in:
        out.append("Altın + BTC + Hisse aynı anda giriş — likidite genişliyor ama hedge talebi de var.")
    if dxy_in and gold_in and by.get("BTCUSD") and by["BTCUSD"].direction == "out":
        out.append("Dolar + Altın giriş, BTC çıkış — klasik risk-off / güvenli liman.")
    return out


def compute() -> dict:
    """Tüm pencereler için likidite rotasyon görünümü (frontend hesap yapmaz).

    OHLCV serileri TEK SEFER yüklenir (sembol başına 1 dosya); pencereler bu
    bellekteki seriler üstünden hesaplanır (tekrar disk/parse yok)."""
    basket = _basket()
    needed = {sym for (sym, _l, _k) in basket} | {"DXY", "VIX"}
    series: Series = {}
    for sym in needed:
        s = _series(sym)
        if s is not None:
            series[sym] = s

    windows: list[dict] = []
    for wname, n in WINDOWS.items():
        macro = _macro_for_window(n, series)
        assets = [
            af
            for (sym, label, kind) in basket
            if (af := _asset_flow(sym, label, kind, n, macro, series)) is not None
        ]
        assets.sort(key=lambda a: a.flow_score, reverse=True)
        regime, reasons = _regime(assets, macro)
        windows.append(
            {
                "window": wname,
                "assets": [
                    {
                        "symbol": a.symbol,
                        "label": a.label,
                        "kind": a.kind,
                        "return_pct": a.ret,
                        "volume_change_pct": a.volume_change_pct,
                        "tvl_change_pct": a.tvl_change_pct,
                        "flow_score": a.flow_score,
                        "direction": a.direction,
                    }
                    for a in assets
                ],
                "regime": regime,
                "regime_reasons": reasons,
                "contradictions": _contradictions(assets),
            }
        )
    return {"windows": windows, "basket_size": len(basket)}
