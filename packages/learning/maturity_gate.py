"""I2 — Olgunluk Kapısı (Maturity Gate): "bu kanıta güvenilir mi?" sorusunun
TEK ortak cevabı.

Amaç (owner talebi 2026-07-05, `docs/LEARNING_INTEGRATION_REPORT.md`): bugün her
öğrenici "güvenilir mi?" kapısını KENDİ içinde taşıyor (kimi edge_report'a, kimi
Wilson'a, kimi min-örnek'e bakıyor) → tutarsız + her yeni öğrenicide tekrar. Bu
modül üç parçayı tek fonksiyonda birleştirir:
  1. Yeterli örnek var mı? (min-sample)
  2. Net sinyal var mı? (kaynağın hükmü ayırt edici mi)
  3. Edge stabil mi? (`edge_report.safe_to_autotune` — otomatik-ayara güvenli mi)

Çıktı = olgunluk basamağı (0-3), otomasyon merdiveninin (rapor §5) evidence
tarafı:
  0 INSUFFICIENT — az örnek (henüz ölçüm bile güvenilmez)
  1 OBSERVED     — yeterli örnek ama net sinyal yok (gürültü)
  2 PROPOSABLE   — net sinyal ama edge stabil değil → owner ÖNERİ seviyesi
  3 ACTIONABLE   — net sinyal + edge stabil → dar-bant OTO seviyesi (owner-flag'li)

KIRMIZI ÇİZGİ: bu kapı yalnızca "kanıt ne kadar olgun" der; TERFİYİ YAPMAZ.
Basamak 2/3'e ulaşmak bile canlıya dokunmaz — terfi/oto-uygula ayrı (I4/I5),
owner kırmızı çizgileri (yön motoru + execution) orada korunur.

SALT-GÖZLEM / PAPER_SAFE. Saf fonksiyon — durum tutmaz, I/O yapmaz.
"""
from __future__ import annotations

# Kalibrasyon/summary konvansiyonuyla aynı (istatistiksel anlamlılık tabanı).
MIN_SAMPLES = 20

# Kaynakların "net sinyal" hükümleri (ayırt edici / kararlı / kanıtlı). INVERSE de
# NET bir sinyaldir (ters ama güçlü kanıt) → zayıf değildir.
CLEAR_VERDICTS = frozenset({
    "DISCRIMINATES", "INVERSE", "STABLE", "CALIBRATED", "RESOLVED", "READY", "PROPOSED",
})
# Net-olmayan / bekleyen hükümler.
WEAK_VERDICTS = frozenset({
    "FLAT", "NO_SPLIT", "INSUFFICIENT", "PENDING", "UNSTABLE", "PRIOR", "NOT_READY",
    "OBSERVED", "DRIFT",
})

_LEVEL_NAME = {0: "INSUFFICIENT", 1: "OBSERVED", 2: "PROPOSABLE", 3: "ACTIONABLE"}


def _is_clear(verdict: str | None) -> bool:
    return verdict is not None and str(verdict).upper() in CLEAR_VERDICTS


def assess(
    *,
    n_samples: int | None,
    verdict: str | None,
    edge_safe: bool | None = None,
    min_samples: int = MIN_SAMPLES,
) -> dict:
    """Bir kanıtın olgunluk basamağı (0-3) + gerekçe. Saf; yan etki yok.

    `edge_safe`: sistemin GLOBAL edge stabilitesi (`edge_report.safe_to_autotune`).
    None → bilinmiyor/uygulanamaz (basamak-3 için stabil şartı ARANMAZ, yalnız
    basamak-2'de kalınmaz; edge açıkça False ise basamak-3 verilmez)."""
    if not n_samples or n_samples < min_samples:
        return _out(0, "az_ornek", n_samples, verdict, edge_safe)
    if not _is_clear(verdict):
        return _out(1, "net_sinyal_yok", n_samples, verdict, edge_safe)
    if edge_safe is False:
        return _out(2, "net_sinyal_edge_stabil_degil", n_samples, verdict, edge_safe)
    return _out(3, "net_sinyal_edge_stabil", n_samples, verdict, edge_safe)


def _out(level: int, reason: str, n, verdict, edge_safe) -> dict:
    return {
        "level": level,
        "maturity": _LEVEL_NAME[level],
        "reason": reason,
        "ready_to_propose": level >= 2,   # I4 terfi hattı bu bayrağı okur
        "ready_to_autotune": level >= 3,  # I5/oto-uygula bu bayrağı okur (owner-flag ayrı)
        "inputs": {"n_samples": n, "verdict": verdict, "edge_safe": edge_safe},
    }


__all__ = ["CLEAR_VERDICTS", "MIN_SAMPLES", "WEAK_VERDICTS", "assess"]
