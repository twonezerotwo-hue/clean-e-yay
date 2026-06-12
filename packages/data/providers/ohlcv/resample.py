"""OHLCV resample — alt TF barlarından üst TF barı üretir.

Yöntem (T1):
- 4h = 1h barlarının epoch//14400 bucket'larında birleşimi.
- 1w = 1d barlarının ISO hafta (yıl, hafta) bucket'larında birleşimi;
  bar ts'i haftanın Pazartesi 00:00 UTC'sidir.
- open = bucket'ın ilk barının open'ı, high = max, low = min,
  close = son barın close'u, volume = toplam (hepsi None ise None).
- Son (oluşmakta olan) bucket dahildir — gerçek, kısmi mum.
- `source = "resampled:<base_tf>"`; verified = tüm üye barlar verified ise.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar, Timeframe

_BUCKET_SECONDS: dict[str, int] = {"15m": 900, "1h": 3600, "4h": 14400}


def _bucket_start(ts: datetime, target_tf: Timeframe) -> datetime:
    if target_tf == "1w":
        # ISO hafta: Pazartesi 00:00 UTC
        day = ts.astimezone(UTC)
        monday = day - timedelta(days=day.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sec = _BUCKET_SECONDS[target_tf]
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp((epoch // sec) * sec, tz=UTC)


def resample(bars: list[OHLCVBar], target_tf: Timeframe) -> list[OHLCVBar]:
    """Sıralı (veya sırasız) alt-TF barlarını target_tf barlarına çevirir."""
    if not bars:
        return []
    base_tf = bars[0].timeframe
    ordered = sorted(bars, key=lambda b: b.ts)
    groups: dict[datetime, list[OHLCVBar]] = {}
    for b in ordered:
        groups.setdefault(_bucket_start(b.ts, target_tf), []).append(b)
    out: list[OHLCVBar] = []
    for start in sorted(groups):
        members = groups[start]
        vols = [m.volume for m in members if m.volume is not None]
        out.append(
            OHLCVBar(
                symbol=members[0].symbol,
                timeframe=target_tf,
                ts=start,
                open=members[0].open,
                high=max(m.high for m in members),
                low=min(m.low for m in members),
                close=members[-1].close,
                volume=sum(vols) if vols else None,
                source=f"resampled:{base_tf}",
                verified=all(m.verified for m in members),
            )
        )
    return out
