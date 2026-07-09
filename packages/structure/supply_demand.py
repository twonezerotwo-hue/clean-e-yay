"""Supply/Demand zon dedektörü — owner yapısal sistemi (EVIDENCE only).

Owner "S/R + likidite %25" kanadının eksik parçası (zones/engine.py'de S/D
kapsam dışıydı). SMC mantığı: güçlü ANİ hareketin (impulse) BAŞLADIĞI yerde
kurumsal emir birikimi vardır → o köken mumu bir "zon"dur.

- Demand (talep): güçlü YUKARI impulse'un köken barı → alıcı bölgesi (destek).
- Supply (arz): güçlü AŞAĞI impulse'un köken barı → satıcı bölgesi (direnç).
- Mitigasyon: fiyat sonradan zona geri girip içinden geçtiyse zon "kullanıldı"
  (mitigated) → taze (unmitigated) zonlar daha değerli.

Impulse ölçüsü ATR-normalize (sembol/TF-adil). Saf fonksiyon, look-ahead yok,
uydurma seviye yok (yetersiz → boş). Canlıya BAĞLI DEĞİL.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.providers.technical.indicators import atr as _atr
from packages.data.types import OHLCVBar

_MIN_BARS = 24
_IMPULSE_ATR = 1.5   # köken sonrası hareket bu kadar ATR ise "impulse"
_IMPULSE_WINDOW = 3  # impulse kaç barda ölçülür (köken sonrası)


@dataclass(frozen=True)
class Zone:
    kind: str                 # supply | demand
    top: float
    bottom: float
    origin_index: int
    mitigated: bool
    distance_pct: float | None = None  # güncel fiyata imzasız uzaklık (%)


def _mitigated(bars: list[OHLCVBar], top: float, bottom: float, after: int) -> bool:
    """Köken sonrası bir bar zona geri girdi mi (low≤top ve high≥bottom)."""
    return any(b.low <= top and b.high >= bottom for b in bars[after:])


def detect(
    bars: list[OHLCVBar], *, atr_mult: float = _IMPULSE_ATR, window: int = _IMPULSE_WINDOW
) -> list[Zone]:
    """S/D zonlarını çıkar (köken + mitigasyon). Yetersiz veri → []."""
    if len(bars) < _MIN_BARS:
        return []
    a = _atr(bars)
    if not a or a <= 0:
        return []
    thr = atr_mult * a
    price = bars[-1].close
    zones: list[Zone] = []
    # Köken barı i; i+1..i+window impulsif mi? (köken barının kendisi patlamaz;
    # patlama sonraki barlarda → köken taze birikim bölgesi.)
    for i in range(1, len(bars) - window - 1):
        origin = bars[i]
        after = bars[i + 1 : i + 1 + window]
        up_move = max(b.high for b in after) - origin.high
        dn_move = origin.low - min(b.low for b in after)
        if up_move >= thr and up_move >= dn_move:
            top = max(origin.open, origin.close)   # gövde üstü
            bottom = origin.low                    # fitil dibi
            zones.append(Zone("demand", round(top, 8), round(bottom, 8), i,
                              _mitigated(bars, top, bottom, i + 1 + window)))
        elif dn_move >= thr and dn_move > up_move:
            top = origin.high
            bottom = min(origin.open, origin.close)
            zones.append(Zone("supply", round(top, 8), round(bottom, 8), i,
                              _mitigated(bars, top, bottom, i + 1 + window)))
    # Dedup: tek impulse birçok köken üretir (önceki sakin barlar da hareketi
    # "görür"). Örtüşen aynı-tür zonlarda impulse'a EN YAKIN tabanı (en güncel
    # origin) tut → gerçek SMC zonu, gürültü değil.
    deduped: list[Zone] = []
    for z in sorted(zones, key=lambda x: x.origin_index):
        hit = None
        for j, e in enumerate(deduped):
            if e.kind == z.kind and not (z.top < e.bottom or z.bottom > e.top):
                hit = j
                break
        if hit is None:
            deduped.append(z)
        elif z.origin_index > deduped[hit].origin_index:
            deduped[hit] = z

    # Uzaklık damgası (güncel fiyata).
    out: list[Zone] = []
    for z in deduped:
        mid = (z.top + z.bottom) / 2.0
        dist = abs(mid - price) / price * 100 if price > 0 else None
        out.append(Zone(z.kind, z.top, z.bottom, z.origin_index, z.mitigated,
                        round(dist, 4) if dist is not None else None))
    return out


def nearest(bars: list[OHLCVBar], **kw) -> dict:
    """Güncel fiyata en yakın TAZE (unmitigated) demand (altta) + supply (üstte).

    Owner setup'ı için: long demand'dan döner, short supply'dan reddedilir."""
    price = bars[-1].close if bars else 0.0
    zones = [z for z in detect(bars, **kw) if not z.mitigated]
    dem = [z for z in zones if z.kind == "demand" and z.top <= price]
    sup = [z for z in zones if z.kind == "supply" and z.bottom >= price]
    nd = max(dem, key=lambda z: z.top, default=None)     # fiyata en yakın alttaki
    ns = min(sup, key=lambda z: z.bottom, default=None)   # fiyata en yakın üstteki
    return {"demand": nd, "supply": ns, "active_count": len(zones)}


__all__ = ["Zone", "detect", "nearest"]
