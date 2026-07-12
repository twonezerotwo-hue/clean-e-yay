"""Onaylı bölge etkisi — owner analizini SL/TP yerleşimine bağlayan dikiş.

Owner kararı (2026-07-12): önerici analizi owner iptal edene kadar ONAYLI;
onaylıysa canlı işlemin giriş/çıkış YERLEŞİMİ bu bölgeleri hesaba katar,
iptal edilirse sistem bugünkü gibi (bölgesiz) skor üretir.

KIRMIZI ÇİZGİ DİSİPLİNİ: `zone_influence.enabled` (thresholds YAML) DEFAULT
FALSE — kapalıyken SL/TP BAYT-AYNI (bu modül hiç çağrılmaz gibi davranır).
Canlıya açma yolu owner yasası: 5y çok-rejim kanıt + owner'ın flag'i iki
ortamda açması (YAML git ile taşınır; lokalde worker restart gerekir).

v1 etkisi DAR ve mekanik (owner gramerinin iki kuralı; yön/skor DEĞİŞMEZ):
- **TP bölge önünde**: LONG'da giriş ile TP arasında onaylı bölge varsa TP
  bölgenin ALT kenarına çekilir (bölge = direnç; kâr bölge önünde alınır).
  Çekilmiş TP risk/ödülü `min_rr_after` altına düşürecekse DOKUNULMAZ.
- **SL bölge arkasında**: SL onaylı bölgenin İÇİNE denk geliyorsa bölgenin
  arkasına taşınır (LONG: alt kenarın pad kadar altı — owner: "desteğin %X
  altına"; bölge ortasında stop = gürültüyle stopout).
SHORT ayna simetriği. Owner manuel işlemleri MUAF (owner kendi kararını verir).

Bölgeler: zone_proposer artifact'ı ∩ zone_approval (owner iptal etmedikçe
onaylı). Asla raise etmez; her hata = etki yok (bugünkü davranış).
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds


def _cfg() -> dict:
    try:
        return dict(load_thresholds().get("zone_influence") or {})
    except Exception:
        return {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def approved_zones(symbol: str) -> list[dict]:
    """Sembolün ONAYLI önerici bölgeleri [{low, high, confluence}, ...].

    Kaynak: zone_proposer artifact (günlük) + zone_approval defteri (owner
    iptal etmedikçe onaylı). Artifact/defter yoksa boş liste — etki yok."""
    try:
        from packages.learning import zone_approval, zone_proposer

        art = zone_proposer._load() or {}
        for a in art.get("assets") or []:
            if str(a.get("symbol")) != str(symbol).upper():
                continue
            out = []
            for z in a.get("zones") or []:
                low, high = float(z["low"]), float(z["high"])
                if zone_approval.verdict_for(symbol, low, high) == "onayli":
                    out.append({"low": low, "high": high,
                                "confluence": int(z.get("confluence", 0))})
            return out
        return []
    except Exception:
        return []


def adjust_targets(
    symbol: str,
    side: str,
    entry: float,
    sl: float,
    tp: float,
    *,
    zones: list[dict] | None = None,
) -> tuple[float, float, list[str]]:
    """Onaylı bölgelere göre (sl, tp, notlar). Bölge yoksa aynen geri döner.

    Saf hesap: `zones` verilirse dışarıdan (test); verilmezse approved_zones.
    Çağıran flag'i kontrol eder — bu fonksiyon flag okumaz (test edilebilirlik)."""
    cfg = _cfg()
    pad = float(cfg.get("pad_pct", 0.005))
    min_rr_after = float(cfg.get("min_rr_after", 0.8))
    zs = zones if zones is not None else approved_zones(symbol)
    notes: list[str] = []
    if not zs or entry <= 0 or side not in {"long", "short"}:
        return sl, tp, notes

    if side == "long":
        # TP bölge önünde: giriş-TP arasındaki en yakın bölgenin alt kenarı.
        blocking = [z for z in zs if entry < z["low"] < tp]
        if blocking:
            near = min(blocking, key=lambda z: z["low"])
            new_tp = near["low"]
            risk = entry - sl
            if risk > 0 and (new_tp - entry) / risk >= min_rr_after:
                notes.append(f"zone_tp_front({tp:.4f}->{new_tp:.4f})")
                tp = new_tp
            else:
                notes.append("zone_tp_skip_rr")
        # SL bölge arkasında: SL bölge içindeyse alt kenarın pad altına.
        inside = [z for z in zs if z["low"] <= sl <= z["high"]]
        if inside:
            behind = min(inside, key=lambda z: z["low"])["low"] * (1 - pad)
            if behind < entry:
                notes.append(f"zone_sl_behind({sl:.4f}->{behind:.4f})")
                sl = behind
    else:  # short — ayna
        blocking = [z for z in zs if tp < z["high"] < entry]
        if blocking:
            near = max(blocking, key=lambda z: z["high"])
            new_tp = near["high"]
            risk = sl - entry
            if risk > 0 and (entry - new_tp) / risk >= min_rr_after:
                notes.append(f"zone_tp_front({tp:.4f}->{new_tp:.4f})")
                tp = new_tp
            else:
                notes.append("zone_tp_skip_rr")
        inside = [z for z in zs if z["low"] <= sl <= z["high"]]
        if inside:
            behind = max(inside, key=lambda z: z["high"])["high"] * (1 + pad)
            if behind > entry:
                notes.append(f"zone_sl_behind({sl:.4f}->{behind:.4f})")
                sl = behind

    return sl, tp, notes


__all__ = ["adjust_targets", "approved_zones", "enabled"]
