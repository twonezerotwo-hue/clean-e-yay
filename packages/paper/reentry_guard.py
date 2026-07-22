"""Tekrar-giriş kilidi — kapanıştan sonra aynı yöne 'bayat sinyalle' anında geri
girmeyi engeller (owner problemi, 2026-07-11).

SORUN: sinyal fire → aç → kârda kapat (owner MANUAL VEYA sistem TP) → 30 sn sonra
AYNI sinyal hâlâ geçerli → `evaluate_open` 'açık pozisyon yok' deyip aynı işlemi
geri açar. Kapanış kararı (owner'ın "yön dönecek" hükmü) açılış yolunda hiç
okunmuyordu — bu modül o hükmü açılış kapısına taşır.

KURAL (owner kararı 'İkisi birden' + 'manuel + kârlı otomatik', 2026-07-11):

  Kilidi KURAN kapanış:
    - close_reason == "MANUAL"  (owner elle kapattı), VEYA
    - normal CLOSED + pnl_usd > 0  (kârlı otomatik: TP/trailing/time-stop kârda).
    FORCE_CLOSED (KILL_SWITCH/RISK_REDUCE) kilit KURMAZ — zorla risk çıkışı
    "hareket bitti" demek değil; zararlı stop da kurmaz (owner 'tüm kapanışlar'
    seçmedi).

  Kilit AÇILIR ancak İKİSİ birden olunca:
    (a) TAZE BAR — kapanıştan bu yana en az bir TF-barı süresi geçti, VE
    (b) SİNYAL DEĞİŞTİ — o anki aday fingerprint'i kilidi kuran işlemin
        fingerprint'inden farklı (aynı bayat sinyal değil). Fingerprint verisi
        eksikse (legacy) bu koşul engellemez (yalnız taze-bar kapısı kalır —
        kalıcı kilit uydurmaz).

  Ters yön (opposite side) = farklı anahtar → hiç kilitlenmez (doğal flip serbest).

MİMARİ (pazarlıksız):
  - ADDITIVE + YALNIZ ENGELLER (no-boost): asla boyut/yön büyütmez.
  - state.recent_trades'ten TÜRETİLİR — yeni kalıcı dosya YOK.
  - SAF / yan-etkisiz / asla raise etmez (kararı düşürmez).
  - Yalnız tik-worker OTOMATİK sinyal açılışına uygulanır; owner manuel açılışı
    (open_position doğrudan) ve manual_ready onayı guard'ı BYPASS eder.
  - Flag default KAPALI (shadow-first): `active=False` iken rapor hesaplanır,
    açılış BAYT-AYNI. Owner kanıtı panelden görüp açar; yanlışsa flag ile geri.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.paper.state import PaperState, Trade

# TF-bar süresi (saniye) — lifecycle ile aynı kaynak; import döngüsü olmasın diye
# burada da tanımlı (aynı sabitler, tek doğruluk: her ikisi de statik piyasa süresi).
_TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


def _arms_lock(t: Trade) -> bool:
    """Bu kapanış tekrar-giriş kilidi kurar mı? (manuel VEYA kârlı normal otomatik)."""
    if t.close_reason == "MANUAL":
        return True
    return t.lifecycle_status == "CLOSED" and t.pnl_usd > 0.0


def _latest_close_for_key(
    trades: list[Trade], symbol: str, side: str, timeframe: str,
    *, cross_tf: bool = False,
) -> Trade | None:
    """(symbol, side, timeframe) için EN SON kapanış (yoksa None). En yeni kapanış
    o anahtarın güncel durumunu belirler: sonradan zararlı stop olduysa kilit yok.

    `cross_tf=True` (owner problemi 2026-07-21) → anahtarttan TIMEFRAME DÜŞER:
    kilit (symbol, side) seviyesinde kurulur. Sebep: kilit TF-hapsindeyken
    "BTC 1h kârda kapandı → 4h aynı tezi hemen açıyor" sızıntısı açık kalıyordu
    (duplicate politikası da TF bazlı: `find_open(symbol, timeframe)`). Böylece
    tek tezin TF kopyalarıyla çoğalması engellenir — defter 4 pozisyon gösterip
    aslında TEK bahis taşımaz. Taze-bar koşulu ADAYIN kendi TF'ine göre ölçülür.
    """
    for t in reversed(trades):
        if t.symbol != symbol or t.side != side:
            continue
        if cross_tf or t.timeframe == timeframe:
            return t
    return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def assess(
    state: PaperState,
    *,
    symbol: str,
    side: str,
    timeframe: str,
    fingerprint: str | None,
    now: datetime,
    cfg: dict | None,
) -> dict:
    """Tekrar-giriş kilidi raporu (saf; asla raise etmez).

    Döner boş dict = kilit yok (o anahtarda kilit kuran kapanış yok). Aksi halde
    rapor: ``active`` (flag açık mı → gerçek engel), ``locked`` (kilitli mi),
    ``fresh_bar`` / ``signal_changed`` (açılma koşulları), gerekçe. Çağıran YALNIZ
    ``active and locked`` iken engeller (shadow-first: kapalıyken rapor gözlem)."""
    cfg = cfg or {}
    trades = getattr(state, "recent_trades", None) or []
    cross_tf = bool(cfg.get("cross_tf", False))
    arming = _latest_close_for_key(trades, symbol, side, timeframe, cross_tf=cross_tf)
    if arming is None or not _arms_lock(arming):
        return {}

    closed_at = _parse_dt(arming.closed_at)
    bar_sec = _TF_SECONDS.get(timeframe)
    secs = (now - closed_at).total_seconds() if closed_at is not None else None
    fresh_bar = secs is not None and bar_sec is not None and secs >= bar_sec
    # Fingerprint eksikse (legacy) sinyal-değişti koşulu ENGELLEMEZ (kalıcı kilit
    # uydurmayalım) → yalnız taze-bar kapısı geçerli kalır.
    if fingerprint is None or arming.fingerprint is None:
        signal_changed = True
    else:
        signal_changed = fingerprint != arming.fingerprint

    released = bool(fresh_bar and signal_changed)
    locked = not released
    reason = None
    if locked:
        parts = []
        if not fresh_bar:
            parts.append("taze_bar_bekleniyor")
        if not signal_changed:
            parts.append("sinyal_ayni")
        reason = "reentry_locked:" + "+".join(parts)

    return {
        "active": bool(cfg.get("enabled", False)),
        "locked": locked,
        "symbol": symbol,
        "side": side,
        "timeframe": timeframe,
        "cross_tf": cross_tf,
        "armed_timeframe": arming.timeframe,
        "armed_by": arming.close_reason,
        "armed_pnl_usd": round(float(arming.pnl_usd), 2),
        "closed_at": arming.closed_at,
        "seconds_since_close": round(secs) if secs is not None else None,
        "bar_seconds": bar_sec,
        "fresh_bar": fresh_bar,
        "signal_changed": signal_changed,
        "reason": reason,
    }


__all__ = ["assess"]
