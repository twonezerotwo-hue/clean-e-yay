"""Owner pozisyon yönetimi — SL/TP değiştir, trailing, kısmi kapat, scale-in, flip.

Pozisyon ID veya SEMBOL ile referanslanır (sembol → o sembolün son açık pozisyonu).
PAPER_SAFE / NO_EXECUTION — gerçek broker emri yok.

Kurallar (17 Kasım P0):
* Pozisyonu büyüten ya da yeni pozisyon açan işlem (scale-in, flip) manuel emirle
  aynı RiskGate'ten geçer (``manual_order.risk_block``); fren aktifken yapılamaz.
* Fiyat ağ çağrısıdır, defter kilidi DIŞINDA çekilir; kilit içinde pozisyonun bu
  arada kapanmadığı ya da boyutunun değişmediği doğrulanır.
* Sayı olmayan ya da sıfır/negatif tutar, oran, fiyat reddedilir; sıfır boyutlu
  kısmi kapama işlem kaydı üretmez.
"""
from __future__ import annotations

from packages.data.ingestion.pipeline import build_snapshot
from packages.data.numeric import is_finite
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state
from packages.paper.guards import price_sanity
from packages.paper.lifecycle import close_position, open_position
from packages.paper.manual_order import risk_block


class PositionOpError(Exception):
    def __init__(self, message: str, code: int = 409) -> None:
        super().__init__(message)
        self.code = code


def _positive(value, message: str) -> float:
    if not is_finite(value) or float(value) <= 0:
        raise PositionOpError(message, 400)
    return float(value)


def _market_price(symbol: str):
    snap = build_snapshot()
    for q in snap.prices:
        if q.symbol == symbol and q.price:
            reason = price_sanity.price_sane_with_ohlcv_reason(symbol, float(q.price))
            if reason is not None:
                return None, snap
            return float(q.price), snap
    return None, snap


def _resolve(state, ref: str):
    """ID tam eşleşme; yoksa sembolün SON açık pozisyonu."""
    for p in state.open_positions:
        if p.id == ref:
            return p
    sym = (ref or "").strip().upper()
    matches = [p for p in state.open_positions if p.symbol == sym]
    return matches[-1] if matches else None


def _require(state, ref):
    pos = _resolve(state, ref)
    if pos is None:
        raise PositionOpError(f"{ref} için açık pozisyon yok", 404)
    return pos


def _locate(ref: str) -> tuple[str, str, float]:
    """Kilit dışı ön okuma (fiyatı kilit dışında çekebilmek için): id, sembol, boyut."""
    pos = _require(paper_state.load(), ref)
    return pos.id, pos.symbol, float(pos.size_usd)


def _unchanged(state, pos_id: str, size_usd: float):
    """Kilit içinde: fiyat çekilirken pozisyon kapanmadıysa ve boyutu değişmediyse onu döndür."""
    for p in state.open_positions:
        if p.id == pos_id:
            if abs(float(p.size_usd) - size_usd) > 1e-6:
                raise PositionOpError("pozisyon bu sırada değişti — tekrar dene")
            return p
    raise PositionOpError("pozisyon bu sırada kapandı")


def _price_or_error(symbol: str, action: str):
    price, snap = _market_price(symbol)
    if price is None or price <= 0:
        raise PositionOpError(f"{symbol} için fiyat yok — {action}")
    return price, snap


def modify_sltp(ref: str, sl: float | None = None, tp: float | None = None) -> dict:
    if sl is None and tp is None:
        raise PositionOpError("sl ya da tp belirt", 400)
    sl = None if sl is None else _positive(sl, "zarar-kes sıfırdan büyük bir fiyat olmalı")
    tp = None if tp is None else _positive(tp, "kâr-al sıfırdan büyük bir fiyat olmalı")
    # T3 — oku→değiştir→yaz tek kilit altında; hata (raise) → yazmadan bırakır.
    with paper_state.transaction("position_ops:modify_sltp") as ps:
        pos = _require(ps, ref)
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        paper_audit.record("MODIFY_SLTP", position_id=pos.id, symbol=pos.symbol, reason=f"sl={pos.sl} tp={pos.tp}")
        return {"position_id": pos.id, "symbol": pos.symbol, "sl": pos.sl, "tp": pos.tp}


def set_trailing(ref: str, distance_pct: float, activate_pct: float | None = None) -> dict:
    distance = _positive(distance_pct, "trailing mesafesi sıfırdan büyük olmalı")
    if distance >= 1:
        raise PositionOpError("trailing mesafesi %100'den küçük olmalı", 400)
    if activate_pct is not None and (not is_finite(activate_pct) or activate_pct < 0):
        raise PositionOpError("trailing başlama eşiği sıfır ya da pozitif bir sayı olmalı", 400)
    pos_id, symbol, size = _locate(ref)
    price, _ = _market_price(symbol)
    with paper_state.transaction("position_ops:set_trailing") as ps:
        pos = _unchanged(ps, pos_id, size)
        pos.trail_distance_pct = distance
        if activate_pct is not None:
            pos.trail_activate_pct = float(activate_pct)
        elif pos.trail_activate_pct is None:
            pos.trail_activate_pct = 0.01
        pos.trail_peak = price if price else (pos.current_price or pos.entry_price)
        pos.trail_active = False
        paper_audit.record("SET_TRAILING", position_id=pos.id, symbol=pos.symbol, reason=f"dist={distance}")
        return {
            "position_id": pos.id, "symbol": pos.symbol,
            "trail_distance_pct": pos.trail_distance_pct, "trail_peak": pos.trail_peak,
        }


def partial_close(ref: str, fraction: float | None = None, size_usd: float | None = None) -> dict:
    if size_usd is not None:
        _positive(size_usd, "kapatılacak tutar sıfırdan büyük olmalı")
    elif fraction is not None:
        if not is_finite(fraction) or not 0 < float(fraction) <= 1:
            raise PositionOpError("kapatma oranı 0 ile 1 arasında olmalı (ör. 0.5)", 400)
    else:
        raise PositionOpError("oran (ör. 0.5) ya da tutar belirt", 400)
    pos_id, symbol, size = _locate(ref)
    price, _ = _price_or_error(symbol, "kapatılamaz")
    with paper_state.transaction("position_ops:partial_close") as ps:
        pos = _unchanged(ps, pos_id, size)
        csize = float(size_usd) if size_usd is not None else pos.size_usd * float(fraction)
        csize = min(csize, pos.size_usd)
        if round(csize, 2) <= 0:
            raise PositionOpError("kapatılacak tutar sıfıra yuvarlanıyor — işlem kaydı açılmadı", 400)
        trade = close_position(ps, pos, exit_price=price, reason="MANUAL", close_size=csize)
        remaining = next((p.size_usd for p in ps.open_positions if p.id == pos.id), 0.0)
        return {
            "position_id": pos.id, "symbol": pos.symbol,
            "closed_usd": round(csize, 2), "pnl_usd": trade.pnl_usd,
            "remaining_usd": round(remaining, 2),
        }


def scale_in(ref: str, add_size_usd: float) -> dict:
    add = _positive(add_size_usd, "eklenecek tutar sıfırdan büyük olmalı")
    pos_id, symbol, size = _locate(ref)
    price, snap = _price_or_error(symbol, "eklenemez")
    with paper_state.transaction("position_ops:scale_in") as ps:
        pos = _unchanged(ps, pos_id, size)
        blocked = risk_block(ps, snap)
        if blocked is not None:
            raise PositionOpError(blocked)
        if add > ps.equity_usd:
            raise PositionOpError("yetersiz bakiye")
        old = float(pos.size_usd)
        new = old + add
        # Ortalama giriş = toplam dolar / toplam miktar (miktar = dolar / fiyat). Dolar
        # ağırlıklı aritmetik ortalama kâr-zararı yanlış gösterir.
        pos.entry_price = new / (old / pos.entry_price + add / price)
        pos.size_usd = round(new, 2)
        paper_audit.record("SCALE_IN", position_id=pos.id, symbol=pos.symbol, size=add, price_used=price)
        return {"position_id": pos.id, "symbol": pos.symbol, "size_usd": pos.size_usd, "avg_entry": pos.entry_price}


def flip(ref: str) -> dict:
    pos_id, symbol, size = _locate(ref)
    price, snap = _price_or_error(symbol, "ters çevrilemez")
    with paper_state.transaction("position_ops:flip") as ps:
        pos = _unchanged(ps, pos_id, size)
        # Ters çevirme yeni pozisyon açar: kapatmadan ÖNCE RiskGate'e sorulur, engel
        # varsa hiçbir şey yapılmaz (yarım kalmış flip yok). Yalnız kapatmak serbesttir.
        blocked = risk_block(ps, snap)
        if blocked is not None:
            raise PositionOpError(f"{blocked}. Yalnız kapatmak istersen 'kapat' yaz")
        sym = pos.symbol
        new_side = "short" if pos.side == "long" else "long"
        trade = close_position(ps, pos, exit_price=price, reason="MANUAL")
        newpos = open_position(
            ps, symbol=sym, side=new_side, entry_price=price, size_multiplier=0.0,
            manual=True, size_usd_override=size, open_reason="owner_flip",
            snapshot_id=snap.snapshot_id,
        )
        paper_audit.record("FLIP", position_id=newpos.id, symbol=sym, side=new_side, size=size, price_used=price)
        return {
            "closed_pnl_usd": trade.pnl_usd, "new_position_id": newpos.id,
            "symbol": sym, "new_side": new_side, "size_usd": size, "entry_price": price,
        }
