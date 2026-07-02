"""F5-3 — aktivasyon watchdog'u: guard_safety desenini TÜM owner-flag
aktivasyonlarına genelleştiren standart outcome-izleyici.

Ne yapar: kayıtlı her owner-flag'in HAM durumunu (thresholds/env) izler.
OFF→ON geçişinde (owner aktivasyonu) eşleştirilmiş baseline expectancy
damgalanıp izleme açılır; yeterli yeni outcome birikince post-enable
expectancy baseline ile kıyaslanır:

  post ≥ baseline → CONFIRMED (aktivasyon zararsız/yararlı, izleme kapanır)
  post <  baseline → DEGRADED  (öneri: "flag'i kapatmayı değerlendir")

guard_safety'den BİLİNÇLİ FARK (🟢 sınıf — davranış değiştirmez):
watchdog HİÇBİR ŞEYİ OTO-KAPATMAZ, override/config YAZMAZ — yalnız ölçer
ve önerir. Oto-kapatma her flag'in engine seam'ine kill-switch bağlamayı
gerektirir (davranış değişikliği = ayrı 🟡 iş); buradaki sözleşme salt
gözlemdir. Yön guard'larının oto-kapatlı kasası guard_safety'de KALIR
(o beş guard bu kayıt listesinde YOKTUR — çifte izleme olmaz).

Dürüstlük sınırı (guard_safety ile aynı): post-enable expectancy GLOBAL'dir;
etki rejim kaymalarıyla karışabilir. Bu bir A/B optimizer değil, "aktivasyon
sonrası genel performans çöktü mü" fail-safe göstergesidir.

Tetik off-tick (learning_worker). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT, load_thresholds
from packages.learning import weight_rollback

_LOCK = threading.Lock()
_HISTORY_CAP = 100

_MIN_OUTCOMES_DEFAULT = 15
_MAX_AGE_HOURS_DEFAULT = 336.0  # 14 gün; 0 → süre koruması kapalı
_ENV_TRUE = {"1", "true", "yes", "on"}

# İzlenen owner-flag kayıtları. source:
#   ("thresholds", (yol, ...)) — load_thresholds() içinde yürünen anahtar yolu;
#     son değer bool okunur (bool olmayan/eksik → False, uydurma yok).
#   ("env", "VAR") — truthy env bayrağı.
# NOT: guard_safety'nin 5 yön guard'ı BURADA YOK (çifte izleme olmasın; onların
# oto-kapatlı kasası var). Yeni owner-flag eklendiğinde buraya satır eklenir.
REGISTRY: dict[str, dict] = {
    "news_sentiment_v2": {
        "label": "News sentiment v2 (M1)",
        "source": ("thresholds", ("news", "sentiment_v2")),
    },
    "regime_drop_unavailable_layers": {
        "label": "Rejim dürüst katman modu (F2-3)",
        "source": ("thresholds", ("regime", "drop_unavailable_layers")),
    },
    "consensus_fundamental_v2": {
        "label": "Fundamental v2 (M3)",
        "source": ("thresholds", ("consensus", "fundamental_v2")),
    },
    "sentinel_v2": {
        "label": "Sentinel v2 stres kompoziti (M4)",
        "source": ("thresholds", ("sentinel_v2", "enabled")),
    },
    "correlation_price_returns": {
        "label": "Fiyat-getirisi korelasyonu (F2-2)",
        "source": ("thresholds", ("risk_gates", "correlation_price_returns")),
    },
    "tf_platt": {
        "label": "TF-bazlı Platt kalibrasyonu (F4-1)",
        "source": ("thresholds", ("calibration", "tf_platt")),
    },
    "empirical_pwin": {
        "label": "Ampirik EV/Kelly p(win) (F4-2)",
        "source": ("thresholds", ("empirical_pwin", "enabled")),
    },
    "partial_tp": {
        "label": "Partial-TP + breakeven (F4-3)",
        "source": ("thresholds", ("partial_tp", "enabled")),
    },
    "weight_regime_filter": {
        "label": "Rejim-filtreli ağırlık eğitimi (F3-2)",
        "source": ("env", "WEIGHT_REGIME_FILTER"),
    },
    "mistake_memory_v2": {
        "label": "Mistake memory v2 (F3-3)",
        "source": ("env", "MISTAKE_MEMORY_V2"),
    },
    "expectancy_r_mode": {
        "label": "R-bazlı expectancy (F1-1)",
        "source": ("env", "EXPECTANCY_R_MODE"),
    },
    # T serisi — teknik analiz genişletmesi (owner onayı 2026-07-02, kodlama;
    # aktivasyonlar ayrı tarihli kararlarla).
    "htf_alignment": {
        "label": "Üst-TF hiza filtresi (T-1)",
        "source": ("thresholds", ("technical", "htf_alignment", "enabled")),
    },
    "elliott_confluence": {
        "label": "Elliott × Fib confluence (T-2)",
        "source": ("thresholds", ("technical", "elliott_confluence", "enabled")),
    },
    "sr_strength": {
        "label": "Destek/direnç gücü (T-3)",
        "source": ("thresholds", ("technical", "sr_strength", "enabled")),
    },
    "candle_confirm": {
        "label": "Kilit seviyede mum teyidi (T-4)",
        "source": ("thresholds", ("technical", "candle_confirm", "enabled")),
    },
}


# ------------------------------- store ---------------------------------------

def _store_path() -> Path:
    p = Path(
        os.environ.get("ACTIVATION_WATCHDOG_PATH", "data/runtime/activation_watchdog.json")
    )
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"monitors": {}, "last_seen": {}, "history": []}


def _load() -> dict:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    for key, default in (("monitors", {}), ("last_seen", {}), ("history", [])):
        if not isinstance(data.get(key), type(default)):
            data[key] = default
    return data


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)


# ------------------------------ flag okuma -----------------------------------

def _flag_enabled(key: str) -> bool:
    """Kayıtlı flag'in HAM durumu (eksik/bozuk → False; uydurma yok)."""
    kind, ref = REGISTRY[key]["source"]
    if kind == "env":
        return os.environ.get(ref, "").strip().lower() in _ENV_TRUE
    try:
        node = load_thresholds()
        for part in ref:
            if not isinstance(node, dict):
                return False
            node = node.get(part)
        return bool(node) if isinstance(node, bool) else False
    except (OSError, KeyError, ValueError, TypeError):
        return False


def _raw_states() -> dict[str, bool]:
    return {k: _flag_enabled(k) for k in REGISTRY}


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("ACTIVATION_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _max_age_hours() -> float:
    try:
        return max(
            0.0, float(os.environ.get("ACTIVATION_MONITOR_MAX_AGE_HOURS", _MAX_AGE_HOURS_DEFAULT))
        )
    except (TypeError, ValueError):
        return _MAX_AGE_HOURS_DEFAULT


def _age_hours(enabled_at: str) -> float | None:
    try:
        dt = datetime.fromisoformat(enabled_at)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 3600.0


def _resolve(data: dict, key: str, *, outcome: str, post_expectancy: float,
             post_n: int, reason: str | None = None) -> None:
    mon = data["monitors"].pop(key, None) or {}
    entry = {
        "flag_key": key,
        "outcome": outcome,
        "enabled_at": mon.get("enabled_at"),
        "baseline_expectancy": mon.get("baseline_expectancy"),
        "baseline_n": mon.get("baseline_n"),
        "post_expectancy": post_expectancy,
        "post_n": post_n,
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    if reason:
        entry["reason"] = reason
    data["history"] = ([entry] + data["history"])[:_HISTORY_CAP]


# --------------------------------- çekirdek ----------------------------------

def sync() -> dict:
    """OFF→ON geçişinde izleme aç (baseline damgala); ON→OFF'ta DISARMED kapat.

    İlk görüşte (last_seen yok) zaten-ON flag'ler izlemeye ALINMAZ — yalnız
    snapshot (guard_safety ile aynı owner-niyeti semantiği: geçmişe dönük
    yakıştırma baseline'ı üretilmez)."""
    data = _load()
    raw = _raw_states()
    armed: list[str] = []
    disarmed: list[str] = []
    for key, now_on in raw.items():
        prev = data["last_seen"].get(key)
        mon = data["monitors"].get(key)
        if prev is False and now_on and mon is None:
            base_n, base_exp = weight_rollback.pre_apply_expectancy(window=_min_outcomes())
            data["monitors"][key] = {
                "enabled_at": datetime.now(UTC).isoformat(),
                "baseline_expectancy": base_exp,
                "baseline_n": base_n,
            }
            armed.append(key)
        elif isinstance(mon, dict) and not now_on:
            post_n, post_exp = weight_rollback.post_open_expectancy(
                str(mon.get("enabled_at") or "")
            )
            _resolve(
                data, key, outcome="DISARMED", post_expectancy=post_exp,
                post_n=post_n, reason="owner_disabled",
            )
            disarmed.append(key)
    data["last_seen"] = raw
    _save(data)
    return {"armed": armed, "disarmed": disarmed}


def _check_one(data: dict, key: str, mon: dict) -> dict:
    need = _min_outcomes()
    enabled_at = str(mon.get("enabled_at") or "")
    post_n, post_exp = weight_rollback.post_open_expectancy(enabled_at)
    baseline = float(mon.get("baseline_expectancy", 0.0))

    def _finish(outcome: str, reason: str | None = None) -> dict:
        _resolve(
            data, key, outcome=outcome, post_expectancy=post_exp,
            post_n=post_n, reason=reason,
        )
        out = {
            "flag_key": key, "status": outcome, "post_expectancy": post_exp,
            "baseline_expectancy": baseline, "post_n": post_n,
        }
        if reason:
            out["reason"] = reason
        return out

    if post_n < need:
        max_age = _max_age_hours()
        age = _age_hours(enabled_at)
        if max_age > 0 and age is not None and age >= max_age:
            if post_n == 0:
                return _finish("INCONCLUSIVE", reason="monitor_expired_no_evidence")
            # kısmi kanıtla karar (öneri niteliğinde — aksiyon yok)
            return _finish(
                "DEGRADED" if post_exp < baseline else "CONFIRMED",
                reason="monitor_expired_partial",
            )
        return {"flag_key": key, "status": "monitoring", "post_n": post_n, "need": need}
    # YALNIZ-ÖNERİ: DEGRADED hiçbir flag'i kapatmaz; owner raporu görüp karar verir.
    return _finish("DEGRADED" if post_exp < baseline else "CONFIRMED")


def check() -> list[dict]:
    data = _load()
    results = [
        _check_one(data, key, mon)
        for key, mon in list(data["monitors"].items())
        if isinstance(mon, dict)
    ]
    _save(data)
    return results


def run() -> dict:
    """learning_worker giriş noktası: geçişleri bağla + izlemeleri değerlendir."""
    transitions = sync()
    checks = check()
    return {
        "armed": transitions["armed"],
        "disarmed": transitions["disarmed"],
        "degraded": [c["flag_key"] for c in checks if c["status"] == "DEGRADED"],
        "monitoring": [c["flag_key"] for c in checks if c["status"] == "monitoring"],
        "checks": checks,
    }


def report() -> dict:
    """Observe-only ViewModel: flag başına durum + aktif izleme + geçmiş."""
    data = _load()
    raw = _raw_states()
    need = _min_outcomes()
    flags = []
    for key, meta in REGISTRY.items():
        mon = data["monitors"].get(key)
        progress = None
        if isinstance(mon, dict):
            post_n, post_exp = weight_rollback.post_open_expectancy(
                str(mon.get("enabled_at") or "")
            )
            progress = {
                "enabled_at": mon.get("enabled_at"),
                "baseline_expectancy": mon.get("baseline_expectancy"),
                "baseline_n": mon.get("baseline_n"),
                "post_expectancy": post_exp,
                "post_n": post_n,
                "need": need,
            }
        flags.append({
            "flag_key": key,
            "label": meta["label"],
            "enabled": raw.get(key, False),
            "monitoring": isinstance(mon, dict),
            "monitor": progress,
        })
    return {
        "available": True,
        "recommend_only": True,  # bu watchdog HİÇBİR ŞEYİ oto-kapatmaz
        "min_outcomes": need,
        "monitor_max_age_hours": _max_age_hours(),
        "flags": flags,
        "history": data["history"][:20],
    }


__all__ = ["REGISTRY", "check", "report", "run", "sync"]
