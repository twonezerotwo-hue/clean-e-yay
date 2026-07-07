"""B-1 — Geçmiş çok-modül yeniden-kurma + sadakat (fidelity) harness'i.

Amaç (owner kararı 2026-07-04): cat 6/7 (quantum + konsensüs ağırlığı) canlı
veri birikmesini haftalarca beklemek yerine, GERÇEK 1-2 yıllık fiyat/makro
serilerinden modül skorlarını geçmişe dönük yeniden kurup rejim-çeşitli kanıt
üretmenin ÖNKOŞULU: "yeniden-kurma canlı sistemle bire bir mi?" sorusunu
kanıtlamak.

TASARIM (pazarlıksız):
- Yeniden-kurma CANLI fonksiyonların KENDİSİNİ kullanır (kopya yok → drift yok):
  `technical.compute_snapshot` (touche), `rotation.compute` (quantum),
  `regime.classify` + `consensus._fundamental_v2/_sentinel` (makro modüller).
- LOOK-AHEAD YOK: her indekste yalnız `bars[: i + 1]` görülür (o ana kadar
  kapanmış barlar). Gelecek bar karara sızmaz.
- news modülü geçmişe kurulamaz (geçmiş sentiment saklanmıyor) → NÖTR 50 +
  `news_reconstructed=False` damgası. DATA_POLICY: uydurma veri yok.
- SALT-ÖLÇÜM / İZOLE: `verified` canlı outcome defterine ASLA yazmaz; yalnız
  `data/runtime/backtest_recon.json` fidelity artifact'ı üretir. Ağırlık/
  kalibrasyon/paper state'e temas etmez. Flag `BACKTEST_RECON_ENABLED` (env,
  DEFAULT OFF) → learning worker adımı tam no-op.
- Fidelity kanıtı: son indekste yeniden-kurulan quantum, BAĞIMSIZ canlı yol
  `rotation.get_rotation()` ile kıyaslanır (aynı formül, ayrı çağrı yolu);
  |delta| eşik altındaysa FAITHFUL. Rejim/fundamental/sentinel deterministik
  türevlerdir, aynı artifact'ta gözlem için taşınır. Rejim-çeşitli outcome
  ÜRETİMİ (B-2) ancak bu kapı FAITHFUL derse anlamlıdır.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from packages.consensus.engine import _fundamental_v2, _sentinel
from packages.consensus.engine import build as consensus_build
from packages.data.providers import rotation as rotation_provider
from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
from packages.data.providers.rotation.engine import compute as rotation_compute
from packages.data.providers.technical import compute_snapshot
from packages.data.registry.loader import load_thresholds
from packages.regime.classifier import classify

_ENV_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_OUT = "data/runtime/backtest_recon.json"
# B-2 — izole challenger kanalı (canlı outcome defteri/ağırlık DEĞİL).
_DEFAULT_CHALLENGER_OUT = "data/runtime/backtest_challenger.jsonl"
_DEFAULT_CHALLENGER_META = "data/runtime/backtest_challenger.json"
# Rejim makro girdileri (classifier _liquidity/_appetite katmanları okur).
_MACRO_SYMBOLS = ("DXY", "US10Y", "US02Y", "CPI", "VIX")
# FRED'den geçmişi çekilecek makro seriler (OHLCV cache'te yok — B-2).
_FRED_SYMBOLS = ("US10Y", "US02Y", "CPI")
# Quantum için minimum seri (rotation.compute 32 bar ister); +BTC touche.
_MIN_BARS = 32
# Fidelity eşiği: yeniden-kurulan quantum ile canlı get_rotation farkı bu
# puanın altındaysa FAITHFUL (aynı formül; ufak fark yalnız bar-tazeliği).
_FIDELITY_TOL = 1.0
# B-2 forward-return: kararın outcome'u kaç bar sonra ölçülür (1d → ufuk gün).
_DEFAULT_HORIZON = 5
# Nötr ölü bant: |forward_return| bunun altındaysa FLAT (yön ödülü yok).
_FLAT_BAND = 0.005
# Challenger jsonl okuma tavanı (bozuk/şişme koruması; üretim overwrite eder).
_CHALLENGER_MAX = 5000


def enabled() -> bool:
    return os.environ.get("BACKTEST_RECON_ENABLED", "").lower() in _ENV_TRUE


def challenger_enabled() -> bool:
    """B-2 üretim kapısı — B-1 fidelity'den AYRI (üretim ağır: 1-2 yıl yürür)."""
    return os.environ.get("BACKTEST_CHALLENGER_ENABLED", "").lower() in _ENV_TRUE


def _out_path() -> Path:
    return Path(os.environ.get("BACKTEST_RECON_PATH", _DEFAULT_OUT))


def _challenger_path() -> Path:
    return Path(os.environ.get("BACKTEST_CHALLENGER_PATH", _DEFAULT_CHALLENGER_OUT))


def _challenger_meta_path() -> Path:
    return Path(os.environ.get("BACKTEST_CHALLENGER_META_PATH", _DEFAULT_CHALLENGER_META))


@dataclass
class ReconScores:
    """Bir geçmiş indeksinde yeniden-kurulan modül skorları (salt-gözlem)."""

    index: int
    as_of: str | None
    regime_label: str | None
    quantum: float | None
    fundamental_v2: float | None
    sentinel: float | None
    news_reconstructed: bool = False
    dropped_layers: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class DecisionRecord:
    """B-2 — bir geçmiş kararın challenger kaydı (İZOLE; canlı defter DEĞİL).

    Karar alanları (`direction`/`combined_score`/`dominant_module`/
    `module_contributions`) yalnız `bars ≤ index` görür. Outcome alanları
    (`forward_return`/`directional_return`/`label`) SONRAKİ barlardan türer —
    kararı ETKİLEMEZ, yalnız etiketler (canlı: karar şimdi, sonuç sonra)."""

    as_of: str | None
    index: int
    symbol: str
    regime_label: str | None
    direction: str | None                      # bullish/bearish/neutral (canlı build)
    combined_score: float | None
    dominant_module: str | None
    module_contributions: dict[str, dict] | None  # name → {score, weight, contribution}
    news_reconstructed: bool = False
    dropped_layers: list[str] = field(default_factory=list)
    # Outcome (forward-return — LABEL, karara girmez):
    horizon_bars: int | None = None
    exit_as_of: str | None = None
    forward_return: float | None = None        # close[i+h]/close[i] − 1 (ham)
    directional_return: float | None = None    # yön hesaba katılmış (long/short)
    label: str | None = None                   # WIN/LOSS/FLAT
    error: str | None = None


def _rotation_shim(closes_upto: dict[str, list[float]]):
    """`rotation.compute` sonucunu classifier'ın okuduğu arayüze (status/score/
    direction/evidence) uyarlar. RRotationResult.available → status."""
    res = rotation_compute(closes_upto)
    status = "OK" if res.available else "UNAVAILABLE"
    return SimpleNamespace(
        status=status,
        score=res.score,
        direction=res.direction,
        evidence=list(res.evidence),
    )


def _snap_at(
    bars_by_symbol: dict[str, list],
    macro_by_symbol: dict[str, list],
    index: int,
) -> tuple[SimpleNamespace | None, object | None, str | None, str | None]:
    """Ortak geçmiş yeniden-kurma → (snap, regime, as_of, error).

    B-1 (`reconstruct_at`) ve B-2 (`reconstruct_decision_at`) AYNI snap'ı kullanır
    → aralarında drift olmaz. LOOK-AHEAD YOK: her seri as_of TARİHİNE kadar
    dilimlenir (`ts ≤ as_of`; farklı uzunluk serilerde indeks-hizalama yanlış
    tarihi alırdı — B-1'de yakalanıp düzeltilen bug).

    `bars_by_symbol`: rotasyon+BTC OHLCV barları. `macro_by_symbol`: makro seriler
    (DXY/US10Y/US02Y/CPI/VIX; FRED katmanları anahtarsızsa boş → Likidite düşer)."""
    btc_bars = bars_by_symbol.get("BTCUSD") or []
    if index < 0 or index >= len(btc_bars):
        return None, None, None, "index_out_of_range"
    if index + 1 < _MIN_BARS:
        return None, None, None, "insufficient_bars"

    as_of_ts = btc_bars[index].ts
    as_of = str(as_of_ts)

    # 1) Quantum rotasyon serileri — DATE-hizalı (canlı get_rotation full seri
    #    kullanır; son indekste bu ona birebir denk gelir).
    closes_upto: dict[str, list[float]] = {}
    for key, sym in ROTATION_SYMBOLS.items():
        seq = bars_by_symbol.get(sym) or []
        upto = [b.close for b in seq if b.ts <= as_of_ts]
        if upto:
            closes_upto[key] = upto
    rot_shim = _rotation_shim(closes_upto)

    # 2) BTC 1d touche (kripto rejim katmanı) — canlı builder, bar dilimi.
    btc_tech = compute_snapshot("BTCUSD", "1d", btc_bars[: index + 1])

    # 3) Makro fiyatlar: her serinin as_of'a kadarki SON kapanışı (gelecek yok).
    prices = []
    for sym in _MACRO_SYMBOLS:
        seq = macro_by_symbol.get(sym) or []
        upto = [b for b in seq if b.ts <= as_of_ts]
        if upto:
            prices.append(SimpleNamespace(symbol=sym, price=upto[-1].close))

    snap = SimpleNamespace(
        prices=prices,
        technicals={"BTCUSD": btc_tech},
        technicals_by_tf=None,   # touche → technicals['BTCUSD'] fallback (tek TF)
        headlines=[],            # news geçmişe kurulamaz → _news 50 (nötr, damgalı)
        rotation=rot_shim,
    )
    regime = classify(snap)
    return snap, regime, as_of, None


def reconstruct_at(
    bars_by_symbol: dict[str, list],
    macro_by_symbol: dict[str, list],
    index: int,
) -> ReconScores:
    """`index`'e kadar kapanmış barlarla modül skorlarını yeniden kurar (B-1).

    LOOK-AHEAD YOK (bkz. `_snap_at`). Çıktı B-1 sözleşmesiyle birebir."""
    snap, regime, as_of, err = _snap_at(bars_by_symbol, macro_by_symbol, index)
    if err is not None:
        return ReconScores(index, None, None, None, None, None, error=err)
    return ReconScores(
        index=index,
        as_of=as_of,
        regime_label=regime.label,
        quantum=round(snap.rotation.score, 2),
        fundamental_v2=(
            round(_fundamental_v2(regime), 2) if _fundamental_v2(regime) is not None else None
        ),
        sentinel=(round(_sentinel(regime), 2) if _sentinel(regime) is not None else None),
        news_reconstructed=False,
        dropped_layers=list(getattr(regime, "dropped", []) or []),
    )


def reconstruct_decision_at(
    bars_by_symbol: dict[str, list],
    macro_by_symbol: dict[str, list],
    index: int,
    *,
    symbol: str = "BTCUSD",
) -> DecisionRecord:
    """B-2 — geçmiş kararın CANLI `consensus.build()` ile birleştirilmiş hükmü.

    Kopya yok: yön/dominant_module/module_contributions canlı motorun KENDİSİNDEN
    (aktif champion ağırlıklarıyla) gelir → challenger kaydı canlı defterle aynı
    şekli taşır. Outcome (forward-return) BURADA hesaplanmaz — üretici ekler
    (karar yalnız `bars ≤ index` görür; outcome ayrı, gelecekteki bar)."""
    snap, regime, as_of, err = _snap_at(bars_by_symbol, macro_by_symbol, index)
    if err is not None:
        return DecisionRecord(
            as_of=None, index=index, symbol=symbol, regime_label=None,
            direction=None, combined_score=None, dominant_module=None,
            module_contributions=None, error=err,
        )
    cons = consensus_build(symbol, snap, regime, "1d")
    contribs = {
        m.name: {"score": m.score, "weight": m.weight, "contribution": m.contribution}
        for m in cons.modules
    }
    return DecisionRecord(
        as_of=as_of, index=index, symbol=symbol,
        regime_label=regime.label,
        direction=cons.direction,
        combined_score=cons.score,
        dominant_module=cons.dominant_module,
        module_contributions=contribs,
        news_reconstructed=False,
        dropped_layers=list(getattr(regime, "dropped", []) or []),
    )


def _lookback_days() -> int:
    """Y-3 — `backtest_challenger.lookback_days` (config; 0/yok = mevcut davranış).

    Rejim-çeşitliliği darboğazı pencere kısalığıydı (365 günde DEFENSIVE 5 /
    CRISIS 0 kayıt); makro+ETF serileri (yfinance) zaten 2 yıl taşır, sınır
    yalnız BTC'nin CoinGecko 1d planıydı (ücretsiz katman 365 gün)."""
    try:
        return int((load_thresholds().get("backtest_challenger") or {}).get("lookback_days", 0))
    except (OSError, KeyError, ValueError, TypeError):
        return 0


def _load_series():
    """Rotasyon+BTC OHLCV + makro serileri (1d).

    OHLCV cache'ten (DXY/VIX + rotasyon/BTC). US10Y/US02Y/CPI OHLCV'de YOK →
    FRED geçmişinden (B-2; `FRED_API_KEY` gerekir, yoksa boş → Likidite düşer,
    uydurma yok). FRED ağ çağrısı yapabilir (off-tick learning worker; tik'e sıfır
    etki) — anahtarsızsa hiç denenmez.

    Y-3: `lookback_days` router derinliğini (BTC coingecko=365) aşıyorsa BTC
    serisi yfinance `BTC-USD` (2y) ile derinleştirilir — YALNIZ bu izole
    challenger kanalı; canlı tick/karar OHLCV yönlendirmesi DEĞİŞMEZ."""
    from packages.data.providers.ohlcv import get_bars
    from packages.data.providers.price import fred

    lookback = _lookback_days()
    bars_by_symbol: dict[str, list] = {}
    for sym in set(ROTATION_SYMBOLS.values()) | {"BTCUSD"}:
        bars_by_symbol[sym] = get_bars(sym, "1d") or []
    if lookback > len(bars_by_symbol.get("BTCUSD") or []):
        try:
            from packages.data.providers.ohlcv import yfinance as _yf
            deep = _yf.fetch_by_ticker("BTC-USD", "BTCUSD", "1d") or []
            if len(deep) > len(bars_by_symbol.get("BTCUSD") or []):
                bars_by_symbol["BTCUSD"] = deep[-lookback:]
        except Exception:  # derin seri gelmezse mevcut (365g) seriyle sürer
            pass
    macro_by_symbol: dict[str, list] = {}
    for sym in _MACRO_SYMBOLS:
        if sym in _FRED_SYMBOLS:
            macro_by_symbol[sym] = fred.get_history(sym) or []
        else:
            macro_by_symbol[sym] = get_bars(sym, "1d") or []
    return bars_by_symbol, macro_by_symbol


def fidelity_report() -> dict:
    """Son indekste yeniden-kurma ↔ bağımsız canlı `get_rotation()` kıyası.

    FAITHFUL: |recon.quantum − live.quantum| ≤ tol. Bu, geçmiş yeniden-kurma
    boru hattının (bar dilimi + saf fonksiyonlar) canlı sistemle aynı sonucu
    ürettiğini kanıtlar → B-2 (rejim-çeşitli üretim) yeşil ışık alır."""
    now = datetime.now(UTC).isoformat()
    bars_by_symbol, macro_by_symbol = _load_series()
    btc_bars = bars_by_symbol.get("BTCUSD") or []
    if len(btc_bars) < _MIN_BARS:
        report = {
            "generated_at": now,
            "verdict": "INSUFFICIENT_DATA",
            "reason": f"BTCUSD {len(btc_bars)} bar < {_MIN_BARS}",
            "recon": None,
            "live_quantum": None,
        }
        _write(report)
        return report

    last = len(btc_bars) - 1
    recon = reconstruct_at(bars_by_symbol, macro_by_symbol, last)

    # Bağımsız canlı yol (aynı formül, ayrı çağrı) — quantum ground-truth.
    live = rotation_provider.get_rotation()
    live_q = getattr(live, "score", None)
    delta = (
        round(abs(recon.quantum - live_q), 3)
        if (recon.quantum is not None and live_q is not None)
        else None
    )
    if delta is None:
        verdict = "UNAVAILABLE"
    elif delta <= _FIDELITY_TOL:
        verdict = "FAITHFUL"
    else:
        verdict = "DRIFT"

    report = {
        "generated_at": now,
        "verdict": verdict,
        "quantum_delta": delta,
        "tolerance": _FIDELITY_TOL,
        "live_quantum": round(live_q, 2) if live_q is not None else None,
        "recon": asdict(recon),
        "note": (
            "news geçmişe kurulamaz (nötr 50, damgalı); rejim/fundamental/"
            "sentinel deterministik türev — quantum fidelity girdi boru hattını "
            "doğrular. FAITHFUL → B-2 rejim-çeşitli üretim güvenli."
        ),
    }
    _write(report)
    return report


def _write(report: dict) -> None:
    try:
        p = _out_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # salt-gözlem; yazım başarısızsa worker'ı kesme


# --------------------------- B-2 üretim (izole challenger) ---------------------------

def _label(directional_return: float | None) -> str | None:
    if directional_return is None:
        return None
    if directional_return > _FLAT_BAND:
        return "WIN"
    if directional_return < -_FLAT_BAND:
        return "LOSS"
    return "FLAT"


def _fill_outcome(rec: DecisionRecord, closes: list[float], horizon: int, exit_ts) -> None:
    """rec'i forward-return outcome alanlarıyla doldurur (in-place).

    LABEL yalnız — kararı ETKİLEMEZ. directional_return = yön × forward_return
    (bullish +, bearish −, neutral 0 → nötr sinyalin yön ödülü yok). Ufuk verisi
    yoksa outcome boş kalır (uydurma yok)."""
    i, j = rec.index, rec.index + horizon
    if j >= len(closes):
        return
    entry, exit_ = closes[i], closes[j]
    if not entry:
        return
    fr = (exit_ - entry) / entry
    if rec.direction == "bullish":
        dr = fr
    elif rec.direction == "bearish":
        dr = -fr
    else:
        dr = 0.0
    rec.horizon_bars = horizon
    rec.exit_as_of = str(exit_ts)
    rec.forward_return = round(fr, 6)
    rec.directional_return = round(dr, 6)
    rec.label = _label(dr)


def _fred_present(macro_by_symbol: dict[str, list]) -> bool:
    """FRED faiz/CPI serileri dolu mu → Likidite katmanı tam (B-2 kazanımı)."""
    return all((macro_by_symbol.get(s) or []) for s in _FRED_SYMBOLS)


def produce_outcomes(
    *,
    bars_by_symbol: dict[str, list] | None = None,
    macro_by_symbol: dict[str, list] | None = None,
    symbol: str = "BTCUSD",
    horizon: int | None = None,
    now: datetime | None = None,
) -> dict:
    """B-2 — rejim-çeşitli GERÇEK-veri outcome üretimi (İZOLE challenger kanalı).

    Her geçmiş indekste (as_of ≥ _MIN_BARS bar) kararı canlı `consensus.build()`
    ile yeniden kurar (aktif champion ağırlıkları) + forward-return outcome'u
    (horizon bar sonra) ekler; tüm kayıtları `backtest_challenger.jsonl`'e
    DETERMİNİSTİK yazar (overwrite — aynı geçmiş aynı seti üretir, çift kayıt yok).

    PAZARLIKSIZ İZOLASYON: canlı outcome defterine / ağırlığa / paper state'e ASLA
    yazmaz — yalnız challenger artifact'ları. news nötr+damgalı (geçmişe
    kurulamaz — DATA_POLICY). LOOK-AHEAD YOK: karar `bars ≤ i` görür; son
    `horizon` indeks ATLANIR (ufuk verisi yok → outcome uydurulmaz).

    `bars_by_symbol`/`macro_by_symbol` enjekte edilebilir (test); None → canlı seri."""
    now = now or datetime.now(UTC)
    horizon = horizon or _DEFAULT_HORIZON
    if bars_by_symbol is None or macro_by_symbol is None:
        bars_by_symbol, macro_by_symbol = _load_series()

    bars = bars_by_symbol.get(symbol) or []
    closes = [b.close for b in bars]
    n = len(bars)
    start = _MIN_BARS - 1            # karar için ≥_MIN_BARS bar
    last_decidable = n - horizon - 1  # bu indeksin outcome'u (closes[i+horizon]) var

    records: list[DecisionRecord] = []
    regimes: dict[str, int] = {}
    labels: dict[str, int] = {}
    for i in range(start, last_decidable + 1):
        rec = reconstruct_decision_at(bars_by_symbol, macro_by_symbol, i, symbol=symbol)
        if rec.error is not None:
            continue
        _fill_outcome(rec, closes, horizon, bars[i + horizon].ts)
        records.append(rec)
        if rec.regime_label:
            regimes[rec.regime_label] = regimes.get(rec.regime_label, 0) + 1
        if rec.label:
            labels[rec.label] = labels.get(rec.label, 0) + 1

    meta = {
        "generated_at": now.isoformat(),
        "engine": "backtest_challenger_v1",
        "symbol": symbol,
        "timeframe": "1d",
        "horizon_bars": horizon,
        "bars_total": n,
        "records": len(records),
        "regime_histogram": regimes,   # cat 6/7 kanıtı: rejim çeşitliliği
        "label_histogram": labels,
        "fred_liquidity": _fred_present(macro_by_symbol),
        "news_reconstructed": False,   # damga: haber geçmişe kurulamadı
        "isolation": "challenger-only; canlı outcome/ağırlık/paper'a YAZMAZ",
    }
    _write_challenger(records, meta)
    return {
        "status": "OK",
        "records": len(records),
        "regime_histogram": regimes,
        "label_histogram": labels,
        "horizon_bars": horizon,
        "fred_liquidity": meta["fred_liquidity"],
    }


def _write_challenger(records: list[DecisionRecord], meta: dict) -> None:
    """İzole challenger kanalı: jsonl (satır=kayıt) + json (özet). Overwrite
    (deterministik üretim → çift kayıt yok). Best-effort: yazım hatası worker'ı
    kesmez. Kayıt tavanı `_CHALLENGER_MAX` (şişme koruması)."""
    try:
        p = _challenger_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(asdict(r), ensure_ascii=False, default=str)
            for r in records[-_CHALLENGER_MAX:]
        ]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        mp = _challenger_meta_path()
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def read_challenger(limit: int = _CHALLENGER_MAX) -> list[dict]:
    """İzole challenger kayıtlarını oku (B-3 girdisi; bozuk satır atlanır)."""
    out: list[dict] = []
    try:
        p = _challenger_path()
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def run_if_due(now: datetime | None = None) -> dict:
    """Worker adımı: challenger üretimini INTERVAL-kapılı çalıştırır (her cycle
    değil — üretim ağır, geçmiş yavaş büyür). Meta taze → CACHED."""
    now = now or datetime.now(UTC)
    try:
        interval = int(os.environ.get("BACKTEST_CHALLENGER_INTERVAL_SEC", "86400"))
    except (TypeError, ValueError):
        interval = 86400
    mp = _challenger_meta_path()
    try:
        if mp.exists():
            prev = json.loads(mp.read_text(encoding="utf-8"))
            gen = str(prev.get("generated_at") or "")
            if gen:
                age = (now - datetime.fromisoformat(gen)).total_seconds()
                if 0 <= age < interval:
                    return {"status": "CACHED", "age_sec": int(age),
                            "records": prev.get("records")}
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return produce_outcomes(now=now)
