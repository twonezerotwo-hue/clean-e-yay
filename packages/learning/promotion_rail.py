"""I4 — Terfi Hattı (Promotion Rail): üç terfi modülünün ORTAK omurgası.

Amaç (owner talebi 2026-07-05, `docs/LEARNING_INTEGRATION_REPORT.md`): bugün üç
terfi modülü (`promotion_criteria` shadow-pipeline / `challenger_promotion`
ağırlık / `discovery.promotion` aday) AYNI iskeleti kopyalıyor —
  kanıt → "sayı ≥ eşik" kapısı → Wilson %95 alt-sınır kapısı → READY/NOT_READY →
  governor `STRATEGY_ENABLE` owner-onay paketi (dedupe).
Bu modül o dört ortak parçayı TEK yere indirir; üçü de buradan çağırır. Böylece
"yeni terfi kanalı" = veri toplama + rail çağrıları (istatistik/paket şekli tek
yerde, sapmasız).

BAYT-AYNI refactor: helper'lar mevcut sözlük şekillerini birebir üretir (aynı
anahtarlar, aynı yuvarlama, aynı pass mantığı). Üç modülün mevcut testleri
DEĞİŞMEDEN yeşil kalır; governor paketleri aynı şekilde çıkar.

KIRMIZI ÇİZGİ (Anayasa/CP5): rail terfiyi YAPMAZ — yalnız kriteri ölçer ve
owner-onay paketi SUNAR. Onay bile canlı config/ağırlık/evreni değiştirmez;
terfi owner'ın elle yürüteceği ayrı iştir.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from packages.learning.mistake_memory import wilson_bounds


def count_check(value: int, required: int) -> dict:
    """"sayı ≥ eşik" kapısı → {value, required, pass}. (matched_decisions /
    resolved_disagreements / resolved_decisive TEK şekle iner.)"""
    return {"value": value, "required": required, "pass": value >= required}


def wilson_check(wins: int, n: int, *, rate_key: str) -> dict:
    """Wilson %95 alt-sınır ayrıklık kapısı → {rate_key, wilson_low, wilson_high,
    required, pass}. Üç modülün ORTAK istatistik kapısı: "isabet şans değil"
    iddiası (alt sınır > 0.5). rate_key kanala göre değişir (challenger_win_rate /
    cf_win_rate); geri kalan şekil aynı."""
    ci_low, ci_high = wilson_bounds(wins, n)
    return {
        rate_key: round(wins / n, 4) if n else None,
        "wilson_low": round(ci_low, 4),
        "wilson_high": round(ci_high, 4),
        "required": "wilson_low > 0.5",
        "pass": n > 0 and ci_low > 0.5,
    }


def status_of(checks: dict) -> str:
    """Tüm kapılar geçerse READY, biri bile düşerse NOT_READY."""
    return "READY" if all(chk["pass"] for chk in checks.values()) else "NOT_READY"


def submit_enable(
    *,
    title: str,
    summary: str,
    evidence: dict,
    requested_change: dict,
    rollback_plan: str,
    source: str,
) -> dict | None:
    """READY paketini governor defterine STRATEGY_ENABLE owner-onay önerisi olarak
    sun. proposal_type + zarf SABİT; dedupe `requested_change` anahtarıyla yürür
    (her kanal AYRI anahtar → çakışmaz, her cycle tek PENDING). Terfiyi YAPMAZ.

    Import lazy: yükleme-zamanı döngü yok (mevcut modüllerin `run()` deseni)."""
    from packages.governor import proposals

    return proposals.submit({
        "proposal_type": "STRATEGY_ENABLE",
        "title": title,
        "summary": summary,
        "evidence": evidence,
        "requested_change": requested_change,
        "rollback_plan": rollback_plan,
        "source": source,
    })


__all__ = ["count_check", "status_of", "submit_enable", "wilson_check"]
