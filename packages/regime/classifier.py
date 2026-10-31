"""Makro rejim sınıflandırıcı.

Dört katman (likidite, risk iştahı, kripto momentum, rotasyon) → tek
RegimeLabel. Katman girdileri gerçek snapshot fiyatlarından okunur.

Veri olmayan katman skor ÜRETMEZ, düşer (`RegimeOutput.dropped`); ortalama
kalan katmanlardan alınır ve konsensüste katmansız kalan temel/sentinel
modülleri düşer. DATA_POLICY: uydurma veri yok (sabit default doldurulmaz).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.types import RegimeLabel


@dataclass
class RegimeLayer:
    name: str
    score: float            # 0–100
    direction: str          # bullish / bearish / neutral
    evidence: list[str]


@dataclass
class RegimeOutput:
    label: RegimeLabel
    layers: list[RegimeLayer]
    # F2-3 — veri yetersizliğinden düşen katman adları (flag kapalıyken hep boş).
    dropped: list[str] = field(default_factory=list)
    # Hysteresis (2026-07-13) — band>0 iken ham (eşik-anlık) etiket; band=0'da None.
    raw_label: RegimeLabel | None = None
    # Hysteresis ham etiketi geri tuttu mu (sınır-üstü zıplama engellendi).
    stabilized: bool = False


# ── Rejim hysteresis (2026-07-13, dış denetim P1: stateless 65/50/35 eşikleri
# sınır yakınında 64.9→65.1→64.8 gibi sık rejim değişimi üretiyor; rejim etiketi
# modül ağırlıklarını seçtiği için her flip karar davranışını oynatır). Band>0
# iken etiket değişimi ancak sınırı BAND kadar aşınca kabul edilir; önceki
# etiket süreçler arası küçük runtime dosyasında tutulur (state git'e girmez).
_ORDER = ("CRISIS", "DEFENSIVE", "NEUTRAL", "OFFENSIVE")
_UPPER_BOUND = {"CRISIS": 35.0, "DEFENSIVE": 50.0, "NEUTRAL": 65.0}
_LOWER_BOUND = {"OFFENSIVE": 65.0, "NEUTRAL": 50.0, "DEFENSIVE": 35.0}


def _hysteresis_band() -> float:
    """`regime.hysteresis_band` (default 0.0 = KAPALI = bayt-aynı davranış)."""
    try:
        from packages.data.registry.loader import load_thresholds

        v = (load_thresholds().get("regime") or {}).get("hysteresis_band", 0.0)
        return float(v or 0.0)
    except Exception:
        return 0.0


def _state_path():
    import os
    from pathlib import Path

    return Path(
        os.environ.get("REGIME_STATE_PATH", "data/runtime/regime_state.json")
    )


def _read_prev_label() -> str | None:
    try:
        import json

        prev = json.loads(_state_path().read_text(encoding="utf-8")).get("label")
        return prev if prev in _ORDER else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _write_label(label: str) -> None:
    try:
        import json

        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"label": label}), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        pass  # state yazılamazsa hysteresis bir sonraki tick'te ham etikete düşer


def _stabilize(prev: str | None, raw: str, avg: float, band: float) -> str:
    """Önceki etiketten ayrılmak için sınırın BAND kadar ötesine geçmek gerekir.

    Yukarı geçiş: prev'in üst sınırı + band aşılmalı. Aşağı geçiş: alt sınırı
    − band altına inilmeli. Geçiş kabul edilirse HAM etiket alınır (çok-basamak
    sıçrama — örn. ani çöküşte OFFENSIVE→CRISIS — geciktirilmez)."""
    if prev is None or raw == prev:
        return raw
    if _ORDER.index(raw) > _ORDER.index(prev):
        return raw if avg >= _UPPER_BOUND[prev] + band else prev
    return raw if avg < _LOWER_BOUND[prev] - band else prev


def _direction(score: float) -> str:
    if score >= 55:
        return "bullish"
    if score <= 45:
        return "bearish"
    return "neutral"


def _price(snap: MarketSnapshot, symbol: str) -> float | None:
    for q in snap.prices:
        if q.symbol == symbol and q.price is not None:
            return q.price
    return None


_LIQ_MOM_MEMO: dict = {"key": None, "val": None}


def _archive_liquidity_momentum() -> float | None:
    """Bar arşivinden DXY+US10Y momentum-Likidite skoru (0-100). Üretici tek
    kaynak `flow.liquidity_momentum_score` (M16 v4 ile birebir). Dosya-imza
    memoize (sıcak yol; zaman-bağımsız). Arşiv kapalı/yok/yetersiz → None."""
    try:
        from packages.data.providers.ohlcv import history

        def _sig(sym: str):
            try:
                st = history._path(sym, "1d").stat()
                return (st.st_size, int(st.st_mtime))
            except OSError:
                return None

        key = (history.enabled(), _sig("DXY"), _sig("US10Y"))
        if _LIQ_MOM_MEMO["key"] == key:
            return _LIQ_MOM_MEMO["val"]
        from packages.data.providers.rotation import flow

        dxy = [b.close for b in history.load("DXY", "1d")]
        us10y = [b.close for b in history.load("US10Y", "1d")]
        val = flow.liquidity_momentum_score(dxy, us10y)
        _LIQ_MOM_MEMO["key"], _LIQ_MOM_MEMO["val"] = key, val
        return val
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _liquidity_layer(snap: MarketSnapshot) -> RegimeLayer | None:
    dxy = _price(snap, "DXY")
    us10y = _price(snap, "US10Y")
    us02y = _price(snap, "US02Y")
    cpi = _price(snap, "CPI") or 0.0
    if dxy is None or us10y is None:
        return None  # çekirdek girdi yok — sahte default'la skor üretilmez
    # Momentum-Likidite: Likidite skoru DEĞİŞİM-bazlı gelir (seviye şişmesini
    # kırar → CRISIS görünür). Bar arşivi yoksa seviye formülüne düşer.
    mom = _archive_liquidity_momentum()
    if mom is not None:
        return RegimeLayer(
            name="Likidite",
            score=round(mom, 1),
            direction=_direction(mom),
            evidence=[f"DXY+faiz momentum (v4) {mom:.1f}"],
        )
    # Yüksek DXY + yüksek getiri → likidite daralıyor.
    score = 100.0 - (dxy - 100.0) * 2.0 - (us10y - 4.0) * 5.0
    evidence = [f"DXY {dxy:.2f}", f"US10Y {us10y:.2f}%"]
    if us02y is None:
        # Eğri iki GERÇEK getiri ister; yarısı uydurma eğri hesaplanmaz.
        evidence.append("2s10s veri yok — eğri sinyali atlandı")
    else:
        curve = us10y - us02y  # 2s10s getiri eğrisi spread'i
        # Ters getiri eğrisi (curve<0) → resesyon/sıkılaşma sinyali; ek ceza (cap 15).
        if curve < 0:
            score -= min(abs(curve) * 10.0, 15.0)
        evidence.append(f"2s10s {curve:+.2f}%")
    score = max(0.0, min(100.0, score))
    if cpi:
        # DÜRÜSTLÜK (denetim bulgusu): CPI Likidite SKORUNA girmez — yalnız
        # gösterim (skora katmak FRED-arşiv + 5y tezgâh ister, FAZ-2 işi).
        # Etiket "gösterim" ile "CPI kullanılıyor" yanılsamasını kapatır.
        evidence.append(f"CPI {cpi:.1f} (gösterim; skora girmez)")
    return RegimeLayer(
        name="Likidite",
        score=round(score, 1),
        direction=_direction(score),
        evidence=evidence,
    )


def _appetite_layer(snap: MarketSnapshot) -> RegimeLayer | None:
    vix = _price(snap, "VIX")
    if vix is None:
        return None  # VIX yoksa risk iştahı ölçülemez — katman düşer
    # Düşük VIX → risk iştahı yüksek
    score = max(0.0, min(100.0, 100.0 - (vix - 12.0) * 4.0))
    return RegimeLayer(
        name="Risk İştahı",
        score=round(score, 1),
        direction=_direction(score),
        evidence=[f"VIX {vix:.1f}"],
    )


def _crypto_layer(snap: MarketSnapshot) -> RegimeLayer | None:
    btc_tech = snap.technicals.get("BTCUSD")
    if btc_tech is None:
        return None  # BTC tekniği yoksa nötr 50 uydurulmaz
    base = btc_tech.score
    return RegimeLayer(
        name="Kripto Momentum",
        score=round(base, 1),
        direction=_direction(base),
        evidence=[
            f"BTC RSI {btc_tech.rsi:.1f}" if btc_tech.rsi is not None else "—",
            f"BTC EMA {btc_tech.ema_stack}",
        ],
    )


def _rotation_layer(snap: MarketSnapshot) -> RegimeLayer | None:
    r = snap.rotation
    if r.status == "UNAVAILABLE":
        # Rotasyon verisi yetersizken provider nötr-50 placeholder döner;
        # konsensüs quantum'u da düşürür — rejim katmanı da düşer.
        return None
    return RegimeLayer(
        name="Sermaye Rotasyonu",
        score=r.score,
        direction=r.direction,
        evidence=list(r.evidence),
    )


def classify(
    snap: MarketSnapshot, *, stateful: bool = True, persist: bool = False
) -> RegimeOutput:
    """Rejim etiketi. `stateful=False` → hysteresis durum dosyasına DOKUNMAZ
    (backtest/replay çağrıları canlı rejim hafızasını kirletmesin).

    `persist=True` yalnız tick worker'ın karar turunda verilir: hysteresis
    hafızasının TEK yazarı odur. API/rapor okumaları (persist=False) önceki
    etiketi okuyup aynı sabitlenmiş etiketi gösterir ama dosyaya YAZMAZ.
    Eskiden her GET (cockpit, matris, rapor) kendi önbellek snapshot'ıyla
    etiketi yazıyordu → canlı rejim etiketi (ve modül ağırlıkları) worker'ın
    kendi sırası yerine dashboard isteklerine göre oynayabiliyordu (H10)."""
    names = ("Likidite", "Risk İştahı", "Kripto Momentum", "Sermaye Rotasyonu")
    candidates = (
        _liquidity_layer(snap),
        _appetite_layer(snap),
        _crypto_layer(snap),
        _rotation_layer(snap),
    )
    layers = [layer for layer in candidates if layer is not None]
    dropped = [n for n, layer in zip(names, candidates, strict=True) if layer is None]
    if layers:
        avg = sum(layer.score for layer in layers) / len(layers)
    else:
        # Hiç makro katman yok: skor UYDURULMAZ; etiket en tarafsız NEUTRAL'a
        # düşer (dropped listesi durumu görünür kılar). Bu durumda fiyat verisi
        # de yok demektir → DQS zaten KILL_SWITCH bölgesindedir.
        avg = 50.0
    label: RegimeLabel
    if avg >= 65:
        label = "OFFENSIVE"
    elif avg >= 50:
        label = "NEUTRAL"
    elif avg >= 35:
        label = "DEFENSIVE"
    else:
        label = "CRISIS"
    # Hysteresis (band=0.0 DEFAULT → bu blok atlanır, davranış bayt-aynı).
    band = _hysteresis_band()
    if band > 0.0 and stateful:
        raw = label
        stable = _stabilize(_read_prev_label(), raw, avg, band)
        if persist:
            _write_label(stable)
        return RegimeOutput(
            label=stable, layers=layers, dropped=dropped,
            raw_label=raw, stabilized=(stable != raw),
        )
    return RegimeOutput(label=label, layers=layers, dropped=dropped)
