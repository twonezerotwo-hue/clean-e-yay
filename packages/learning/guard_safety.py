"""CP3 — yön güvenlik kasası (direction safety vault).

`weight_rollback` desenini **herhangi bir flag'li yön guard'ına** genelleştirir:
bir owner bir yön guard'ını canlıya aldığında (config flag OFF→ON) kasa onu izlemeye
alır (enable anındaki eşleştirilmiş baseline expectancy), yeterli yeni outcome
birikince post-enable expectancy'i baseline ile kıyaslar ve **düşerse guard'ı oto-kapatır**
(guard_overrides kill-switch'i; owner config'ine dokunmaz, engine seam'leri OFF okur).

Bağlı guard'lar (hepsi shadow-first; gözlem değeri zaten direction_score'da hesaplanır):
  * chop          — technical.trend_quality.enabled
  * exhaustion    — technical.exhaustion_guard.enabled
  * reversion     — technical.reversion.enabled
  * self_conflict — book_audit.self_conflict_guard.enabled
  * concentration — book_audit.concentration_guard.enabled

KASA İLE AĞIRLIK ROLLBACK'İNİN İKİ FARKI (bilinçli):
  1. Birden çok guard bağımsız izlenir (her guard_key kendi slot'unda).
  2. **Owner-niyeti korunur:** guard enable bir owner aksiyonudur. Bu yüzden kasa
     yalnız KANIT (post < baseline) varken kapatır. Kanıt birikmeden süre dolarsa
     INCONCLUSIVE kapanır ve guard CANLI kalır (ağırlık rollback'i no-evidence'ta
     geri alırdı — orada değişiklik OTONOM uygulanmıştı; burada owner kararı).

GÜVEN/SINIR (dürüst): post-enable expectancy GLOBAL'dir (guard yalnız bazı trade'leri
bloklar; etki rejim kaymalarıyla karışabilir). weight_rollback ile aynı sınır — bu bir
A/B optimizer DEĞİL (o CP4), bir **fail-safe kasa**: enable'dan sonra genel expectancy
çökerse guard'ı geri al. Yön çevirmez, sadece guard'ı bugünkü baseline'a döndürür.

Tetik off-tick (learning_worker); tick sıcak yoluna ek yük yok (law 5).
PAPER_SAFE / NO_EXECUTION: yalnız manifest/override pointer'ı; emir üretmez.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from packages.data.registry import guard_overrides
from packages.data.registry.loader import load_thresholds
from packages.learning import guard_monitor_store as store
from packages.learning import weight_rollback

# guard_key → (insan-okur etiket, thresholds config yolu .enabled bayrağı için).
_GUARDS: dict[str, dict] = {
    "chop": {"label": "Chop (trend kalitesi)", "path": ("technical", "trend_quality")},
    "exhaustion": {"label": "Exhaustion (climax kovalama)", "path": ("technical", "exhaustion_guard")},
    "reversion": {"label": "Reversion (mean-reversion)", "path": ("technical", "reversion")},
    "self_conflict": {"label": "Self-conflict (zıt yön)", "path": ("book_audit", "self_conflict_guard")},
    "concentration": {"label": "Concentration (aynı-yön yığını)", "path": ("book_audit", "concentration_guard")},
}

_MIN_OUTCOMES_DEFAULT = 15
_MONITOR_MAX_AGE_HOURS_DEFAULT = 336.0  # 14 gün; 0 → süre koruması kapalı
_AUTO_DISABLE_OFF = {"0", "false", "no", "off", ""}


def guard_keys() -> list[str]:
    return list(_GUARDS)


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("GUARD_ROLLBACK_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _monitor_max_age_hours() -> float:
    try:
        return max(0.0, float(os.environ.get("GUARD_MONITOR_MAX_AGE_HOURS", _MONITOR_MAX_AGE_HOURS_DEFAULT)))
    except (TypeError, ValueError):
        return _MONITOR_MAX_AGE_HOURS_DEFAULT


def _auto_disable_enabled() -> bool:
    """Oto-kapat ana anahtarı (default AÇIK; `GUARD_AUTO_DISABLE=0` ile recommend-only).
    Kapalıyken rollback kararı ROLLBACK_RECOMMENDED olarak kaydedilir ama override
    YAZILMAZ — owner tek-flag ile uygular (law 4: 'veya tek-flag ile geri alınır')."""
    return os.environ.get("GUARD_AUTO_DISABLE", "1").strip().lower() not in _AUTO_DISABLE_OFF


def _raw_enabled(guard_key: str, thresholds: dict) -> bool:
    """Guard'ın HAM config-enabled bayrağı (override'dan bağımsız)."""
    sec, sub = _GUARDS[guard_key]["path"]
    block = (thresholds.get(sec) or {}).get(sub) or {}
    return bool(block.get("enabled", False))


def _raw_states() -> dict[str, bool]:
    th = load_thresholds()
    return {k: _raw_enabled(k, th) for k in _GUARDS}


def _monitor_age_hours(enabled_at: str) -> float | None:
    try:
        dt = datetime.fromisoformat(enabled_at)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 3600.0


# --------------------------------------------------------------------------
# sync — owner geçişlerini (OFF→ON / ON→OFF) izlemeye bağla
# --------------------------------------------------------------------------

def sync() -> dict:
    """Ham config-enabled geçişlerini tespit et:

      * OFF→ON (owner guard'ı canlıya aldı) → izleme aç + eşleştirilmiş baseline damgala.
        Varsa eski kill-override temizlenir (owner re-promosyonu = taze deneme).
      * ON→OFF (owner guard'ı kapattı) → izleme DISARMED (owner kararı, kasa kapatmadı).

    İLK GÖRÜŞ (last_seen yok) ve guard zaten ON ise → izleme AÇILMAZ; yalnız snapshot
    alınır. Önceden-canlı guard'lar (örn. self_conflict) geriye dönük izlenmez —
    izleme yalnız GELECEKTEKİ geçişleri korur (owner niyeti)."""
    raw = _raw_states()
    last = store.get_last_seen()
    armed: list[str] = []
    disarmed: list[str] = []
    for key, raw_now in raw.items():
        prev = last.get(key)
        active = store.get_active(key)
        if prev is False and raw_now and active is None:
            # taze OFF→ON → eski kill-override'ı düşür, baseline damgala, izle.
            guard_overrides.clear(key)
            base_n, base_exp = weight_rollback.pre_apply_expectancy(window=_min_outcomes())
            store.record_enable(
                key,
                enabled_at=datetime.now(UTC).isoformat(),
                baseline_expectancy=base_exp,
                baseline_n=base_n,
            )
            armed.append(key)
        elif active is not None and not raw_now:
            # owner guard'ı kapattı → izlemeyi sonlandır (kasa kapatmadı).
            post_n, post_exp = weight_rollback.post_open_expectancy(active.get("enabled_at", ""))
            store.resolve(
                key, outcome="DISARMED", post_expectancy=post_exp, post_n=post_n,
                reason="owner_disabled",
            )
            disarmed.append(key)
    store.set_last_seen(raw)
    return {"armed": armed, "disarmed": disarmed}


def adopt(keys: list[str] | None = None) -> dict:
    """Owner aksiyonu: ZATEN AÇIK ama izlenmeyen guard'ları "şu andan itibaren" izlemeye
    al (mode="adopted"). Baseline = enable-öncesi DEĞİL, şu anki eşleştirilmiş pencere
    (guard zaten açıktı) → bu yüzden adopted izleme yalnız SÜRÜKLENME alarmıdır ve
    oto-kapatMAZ (recommend-only, bkz. _apply_rollback). Owner OFF→ON toggle ederse
    transition-modu (kanıtlı, oto-kapatlı) izleme açılır — daha güçlüsü odur.

    `keys` verilmezse tüm uygun guard'lar (canlı + izlenmiyor + kasa-kapatmamış)."""
    raw = _raw_states()
    targets = keys if keys is not None else list(_GUARDS)
    adopted: list[str] = []
    for key in targets:
        if key not in _GUARDS:
            continue
        if not raw.get(key):  # canlı değil → adopte edilemez
            continue
        if store.get_active(key) is not None:  # zaten izleniyor
            continue
        if guard_overrides.is_disabled(key):  # kasa kapatmış → adopte etme
            continue
        base_n, base_exp = weight_rollback.pre_apply_expectancy(window=_min_outcomes())
        store.record_enable(
            key,
            enabled_at=datetime.now(UTC).isoformat(),
            baseline_expectancy=base_exp,
            baseline_n=base_n,
            mode="adopted",
        )
        adopted.append(key)
    return {"adopted": adopted}


# --------------------------------------------------------------------------
# check — aktif izlemeleri değerlendir (CONFIRMED / ROLLED_BACK / monitoring)
# --------------------------------------------------------------------------

def _apply_rollback(guard_key: str, *, post_exp: float, post_n: int, baseline: float,
                    reason: str | None, adopted: bool = False) -> dict:
    """post < baseline → guard'ı geri al. Oto-kapat açıksa override yazılır
    (ROLLED_BACK); kapalıysa yalnız öneri kaydedilir (ROLLBACK_RECOMMENDED).

    `adopted` (zaten-açık guard, eşzamanlı baseline): oto-kapat ANAHTARI ne olursa
    olsun YALNIZ-ÖNERİ — sürüklenme korumadan değil piyasadan olabilir, sessizce
    kapatmak güvenli değil (bkz. modül docstring)."""
    auto = _auto_disable_enabled() and not adopted
    if auto:
        guard_overrides.set_disabled(
            guard_key,
            reason=f"expectancy {post_exp} < baseline {baseline} (n={post_n})",
        )
        status = "ROLLED_BACK"
    else:
        status = "ROLLBACK_RECOMMENDED"
    store.resolve(
        guard_key, outcome=status, post_expectancy=post_exp, post_n=post_n, reason=reason,
    )
    out = {
        "guard_key": guard_key,
        "status": status,
        "post_expectancy": post_exp,
        "baseline_expectancy": baseline,
        "post_n": post_n,
        "auto_disabled": auto,
    }
    if reason:
        out["reason"] = reason
    return out


def _confirm(guard_key: str, *, post_exp: float, post_n: int, baseline: float,
             reason: str | None) -> dict:
    """post ≥ baseline → guard yardımcı; izleme CONFIRMED kapanır, guard CANLI kalır."""
    store.resolve(
        guard_key, outcome="CONFIRMED", post_expectancy=post_exp, post_n=post_n, reason=reason,
    )
    out = {
        "guard_key": guard_key,
        "status": "CONFIRMED",
        "post_expectancy": post_exp,
        "baseline_expectancy": baseline,
        "post_n": post_n,
    }
    if reason:
        out["reason"] = reason
    return out


def _decide(guard_key: str, active: dict, *, post_exp: float, post_n: int,
            reason: str | None = None) -> dict:
    baseline = float(active.get("baseline_expectancy", 0.0))
    adopted = active.get("mode") == "adopted"
    if post_exp < baseline:
        return _apply_rollback(
            guard_key, post_exp=post_exp, post_n=post_n, baseline=baseline, reason=reason,
            adopted=adopted,
        )
    return _confirm(
        guard_key, post_exp=post_exp, post_n=post_n, baseline=baseline, reason=reason,
    )


def _check_one(guard_key: str, active: dict) -> dict:
    need = _min_outcomes()
    enabled_at = str(active.get("enabled_at") or "")
    post_n, post_exp = weight_rollback.post_open_expectancy(enabled_at)

    if post_n < need:
        max_age = _monitor_max_age_hours()
        age_h = _monitor_age_hours(enabled_at)
        if max_age > 0 and age_h is not None and age_h >= max_age:
            if post_n == 0:
                # Kanıt yok + süre doldu → owner niyetine saygı: guard CANLI kalır,
                # izleme INCONCLUSIVE kapanır (ağırlık rollback'inden farkı, bkz. docstring).
                store.resolve(
                    guard_key, outcome="INCONCLUSIVE", post_expectancy=post_exp,
                    post_n=post_n, reason="monitor_expired_no_evidence",
                )
                return {
                    "guard_key": guard_key,
                    "status": "INCONCLUSIVE",
                    "post_n": post_n,
                    "reason": "monitor_expired_no_evidence",
                }
            return _decide(
                guard_key, active, post_exp=post_exp, post_n=post_n,
                reason="monitor_expired_partial",
            )
        return {"guard_key": guard_key, "status": "monitoring", "post_n": post_n, "need": need}

    return _decide(guard_key, active, post_exp=post_exp, post_n=post_n)


def check_guards() -> list[dict]:
    """Tüm aktif izlemeleri değerlendir. Her biri için durum:
    monitoring | CONFIRMED | ROLLED_BACK | ROLLBACK_RECOMMENDED | INCONCLUSIVE."""
    results: list[dict] = []
    for key, active in store.all_active().items():
        if not isinstance(active, dict):
            continue
        results.append(_check_one(key, active))
    return results


def run() -> dict:
    """learning_worker giriş noktası: önce geçişleri bağla (sync), sonra izlemeleri
    değerlendir (check). Defensive değil — worker zaten try/except sarar."""
    transitions = sync()
    checks = check_guards()
    rolled = [c["guard_key"] for c in checks if c["status"] in ("ROLLED_BACK", "ROLLBACK_RECOMMENDED")]
    monitoring = [c["guard_key"] for c in checks if c["status"] == "monitoring"]
    return {
        "armed": transitions["armed"],
        "disarmed": transitions["disarmed"],
        "rolled_back": rolled,
        "monitoring": monitoring,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# report — observe-only view (endpoint/panel)
# --------------------------------------------------------------------------

def report() -> dict:
    """CP3 kasa durumu (observe-only): guard başına ham vs efektif enabled, aktif
    izleme ilerlemesi, kill-override'lar ve son geçmiş. Karar zincirini ETKİLEMEZ."""
    raw = _raw_states()
    overrides = guard_overrides.active()
    active_monitors = store.all_active()
    need = _min_outcomes()
    guards = []
    for key, meta in _GUARDS.items():
        raw_on = raw.get(key, False)
        killed = key in overrides
        mon = active_monitors.get(key)
        progress = None
        if isinstance(mon, dict):
            post_n, post_exp = weight_rollback.post_open_expectancy(str(mon.get("enabled_at") or ""))
            progress = {
                "enabled_at": mon.get("enabled_at"),
                "mode": mon.get("mode", "transition"),
                "baseline_expectancy": mon.get("baseline_expectancy"),
                "baseline_n": mon.get("baseline_n"),
                "post_expectancy": post_exp,
                "post_n": post_n,
                "need": need,
            }
        guards.append({
            "guard_key": key,
            "label": meta["label"],
            "config_enabled": raw_on,
            "vault_disabled": killed,
            # Engine'in gerçekte gördüğü efektif durum (config ON ama kill varsa OFF).
            "effective_enabled": raw_on and not killed,
            "monitoring": isinstance(mon, dict),
            "monitor": progress,
            "override": overrides.get(key),
        })
    return {
        "available": True,
        "auto_disable_enabled": _auto_disable_enabled(),
        "min_outcomes": need,
        "monitor_max_age_hours": _monitor_max_age_hours(),
        "guards": guards,
        "history": store.history(limit=20),
    }


__all__ = ["adopt", "check_guards", "guard_keys", "report", "run", "sync"]
