"""Karar-kanıt tüketicisi — TÜM öğrenmeleri TEK birleşik fikre indirger.

Owner talebi (2026-07-09): dağınık learning'ler (mistake_memory / meta_gate /
reflection / calibration / EV) her karara ayrı ayrı değil, TEK "fikir" olarak
girsin. Bu modül o fikri üretir: her açılış adayına birleşik bir hüküm
(`CONFIRM / CAUTION / AVOID`) + gerekçeler + advisory boyut-ipucu.

MİMARİ KURALLAR (pazarlıksız):
- VARSAYILAN GÖLGE: `advise()` her karara EKLENİR (gözlem) ama boyutu/yönü
  DEĞİŞTİRMEZ. Canlı etki yalnız `LEARNING_ADVISOR_APPLY=1` iken (owner kararı).
- NO-BOOST: advisory yalnız KISAR (size_hint ≤ 1.0). Asla büyütmez. Apply açıkken
  bile boyut yalnızca çarpılıp küçülür — RiskGate ve deterministik taban değişmez.
- OLGUNLUK-KAPILI: her kaynak yalnız gerçek kanıtı varsa hüküm verir; kanıtsız
  kaynak "nötr" kalır (sessiz), fikri saptırmaz.
- UCUZ + DEFANSİF: sıcak yolda çağrılır → yalnız önceden-hesaplanmış girdiler +
  cache'li reflection artifact'ı okunur; asla raise etmez (kararı düşürmez).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

FLAG_APPLY = "LEARNING_ADVISOR_APPLY"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})

# Advisory boyut-ipuçları (yalnız kısma — no-boost).
_SIZE_CAUTION = 0.7
_SIZE_AVOID = 0.0
_SIZE_NEUTRAL = 1.0

# Reflection cache: son sembol dersleri "çoğu kayıp" ise DİKKAT.
_REFLECT_MIN_N = 3
_REFLECT_LOSS_WINPCT = 40.0


def apply_enabled() -> bool:
    """Canlı etki flag'i. KAPALI (default) → advice yalnız gözlem, boyut değişmez."""
    return os.environ.get(FLAG_APPLY, "").strip().lower() in _ENV_TRUE


@dataclass
class Advice:
    stance: str = "CONFIRM"          # CONFIRM | CAUTION | AVOID
    size_hint: float = _SIZE_NEUTRAL  # ≤1.0 (yalnız kısma)
    reasons: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)   # hüküm veren olgun kaynaklar
    applied: bool = False             # canlı boyuta uygulandı mı (flag açıksa)


def _reflection_symbol_memory(symbol: str) -> dict | None:
    """Cache'li reflection digest'inden bu sembolün hafızası (ucuz; artifact okur)."""
    try:
        p = Path(os.environ.get("REFLECTION_PATH", "data/runtime/reflection_digest.json"))
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return (data.get("per_symbol") or {}).get(symbol)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _meta_stance(meta_report: dict | None) -> str | None:
    """meta_gate gölge hükmünü normalize et (GİRME/negatif → CAUTION sinyali)."""
    if not meta_report:
        return None
    v = str(meta_report.get("verdict") or meta_report.get("label") or "").upper()
    if not v:
        return None
    if any(k in v for k in ("AVOID", "GIRME", "GİRME", "NEG", "SKIP", "BLOCK")):
        return "CAUTION"
    if any(k in v for k in ("ENTER", "GIR", "GİR", "POS", "GO")):
        return "CONFIRM"
    return None


def advise(
    *,
    symbol: str,
    timeframe: str,
    regime: str,
    dominant_module: str,
    mistake_action: str,
    meta_report: dict | None = None,
    calibrated_confidence: float | None = None,
    expected_value: float | None = None,
    min_confidence: float = 0.5,
) -> Advice:
    """Tüm learning'leri TEK hükme indirge (EVIDENCE-only, olgunluk-kapılı).

    Her kaynak yalnız gerçek kanıtı varsa oy verir; en katı hüküm (AVOID > CAUTION
    > CONFIRM) kazanır. size_hint yalnız kısar (no-boost). Asla raise etmez."""
    reasons: list[str] = []
    sources: list[str] = []
    stance = "CONFIRM"

    def escalate(to: str) -> None:
        nonlocal stance
        order = {"CONFIRM": 0, "CAUTION": 1, "AVOID": 2}
        if order[to] > order[stance]:
            stance = to

    # 1) mistake_memory (fingerprint istatistiği) — zaten karara bağlı, birleştir.
    ma = (mistake_action or "NEUTRAL").upper()
    if ma == "AVOID":
        escalate("AVOID")
        reasons.append("mistake_memory: AVOID (tekrar eden kayıp)")
        sources.append("mistake_memory")
    elif ma == "WARNING":
        escalate("CAUTION")
        reasons.append("mistake_memory: WARNING")
        sources.append("mistake_memory")

    # 2) meta_gate gölge hükmü.
    if _meta_stance(meta_report) == "CAUTION":
        escalate("CAUTION")
        reasons.append("meta_gate: GİRME eğilimi")
        sources.append("meta_gate")

    # 3) reflection — son benzer işlem dersleri (cache'li, ucuz).
    mem = _reflection_symbol_memory(symbol)
    if mem:
        summ = mem.get("summary") or {}
        n = summ.get("n") or 0
        wp = summ.get("win_pct")
        if n >= _REFLECT_MIN_N and wp is not None and wp < _REFLECT_LOSS_WINPCT:
            escalate("CAUTION")
            reasons.append(f"reflection: son {n} işlem %{wp:.0f} kazandı (zayıf hafıza)")
            sources.append("reflection")

    # 4) kalibre güven + EV (zaten hesaplanmış) — düşükse DİKKAT.
    if calibrated_confidence is not None and calibrated_confidence < min_confidence:
        escalate("CAUTION")
        reasons.append(f"düşük p(win) %{calibrated_confidence * 100:.0f}")
        sources.append("calibration")
    if expected_value is not None and expected_value < 0:
        escalate("CAUTION")
        reasons.append(f"negatif EV {expected_value:+.2f}R")
        sources.append("ev")

    size_hint = {"CONFIRM": _SIZE_NEUTRAL, "CAUTION": _SIZE_CAUTION, "AVOID": _SIZE_AVOID}[stance]
    return Advice(stance=stance, size_hint=size_hint, reasons=reasons, sources=sources)


def to_dict(a: Advice) -> dict:
    return asdict(a)


__all__ = ["FLAG_APPLY", "Advice", "advise", "apply_enabled", "to_dict"]
