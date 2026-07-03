"""Paper trading state — JSON dosyası bazlı kalıcılık.

P1 — robustness: atomik yazım (temp + os.replace), `schema_version`, corrupt
dosya → yedek + default (crash yok), legacy/forward-uyumlu yükleme (bilinmeyen
alanlar atlanır, eksik alanlar default'a düşer). PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds
from packages.paper import audit, execution_sim

SCHEMA_VERSION = 1

STATE_PATH = Path(
    os.environ.get("PAPER_STATE_PATH", "data/runtime/paper_state.json")
)
_LOCK = threading.Lock()

# B2 — geçici dosya-kilidi (Windows) dayanıklılığı. Birden fazla süreç (supervisor
# + keep-alive watchdog'ın spawn'ı) state'i eşzamanlı yazınca, bir sürecin
# `read_text`/`os.replace`'i ötekinin `os.replace`'i sırasında kısa süre kilide
# takılıp PermissionError (WinError 5/32) alabilir. Bu GEÇİCİDİR — bozulma değil.
# Eskiden load() bunu "corrupt" sanıp state'i boş default'la EZİYORDU (gerçek
# veri-kaybı). Artık retry ediyoruz; yalnız gerçek parse hatası onarımı tetikler.
_READ_RETRIES = 5
_RETRY_BASE_SLEEP_S = 0.05

# Süreç-içi son başarıyla okunan ham state. Kalıcı kilitte (retry'lar tükenirse)
# gerçek veriyi koruyabilmek için tutulur — boş default'la read-modify-write
# ezmesini önler.
_LAST_GOOD_RAW: dict | None = None


def _only_known(cls, d: dict) -> dict:
    """Yalnızca `cls` dataclass alanlarını süz — legacy/forward uyumlu yükleme.

    Bilinmeyen alanlar atlanır (yeni şemadan gelen ekstra alanlar eski kodu
    patlatmaz); eksik alanlar dataclass default'una düşer (legacy kayıtlar).
    """
    known = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in known}


@dataclass
class Position:
    id: str
    symbol: str
    side: str             # long / short
    entry_price: float
    current_price: float
    size_usd: float
    sl: float | None
    tp: float | None
    opened_at: str
    fingerprint: str | None = None
    data_verified: bool = False  # quote.verified at open; learning filters non-verified
    predicted_confidence: float | None = None  # calibrated p(win) at open
    raw_confidence: float | None = None        # pre-calibration p(win)
    confidence_source: str | None = None       # identity | fitted | insufficient
    timeframe: str = "1d"  # T0 additive — legacy kayıtlar default "1d" yüklenir
    # T2 — TF time-stop: dolunca TIME_STOP_EXIT. None → time-stop yok
    # (legacy kayıtlar None ile yüklenir; davranış değişmez).
    valid_until: str | None = None
    # P1 — lifecycle state machine (additive; legacy kayıtlar default'a düşer).
    # OPEN → (EXPIRED_PENDING_PRICE | EXIT_PENDING | ERROR_STATE) → terminal Trade.
    lifecycle_status: str = "OPEN"
    time_stop_expired: bool = False
    pending_exit_reason: str | None = None  # neden exit bekliyor (fiyat yoksa)
    open_reason: str | None = None          # learning handoff: karar gerekçesi
    snapshot_id: str | None = None          # learning handoff: kaynak snapshot
    scale_in: bool = False                  # explicit scale-in (default: yok)
    # Signal attribution (additive): karar izi açılışta damgalanır.
    open_dqs: float | None = None           # açılış anındaki DQS
    open_risk_action: str | None = None     # açılış anındaki RiskGate kararı (izinli)
    # Market-session attribution (additive): açılış anındaki seans bağlamı.
    open_session_action: str | None = None              # allow/caution/manual_ready/block
    open_session_phase: str | None = None               # primary market session phase
    open_session_reason: str | None = None
    open_session_size_multiplier: float | None = None   # uygulanan seans çarpanı (≤ 1.0)
    open_session_primary_market_open: bool | None = None
    open_session_evidence: str | None = None            # "; "-joined evidence
    # Konviksiyon-kademeli risk (additive): açılışta kademe + trailing parametreleri.
    tier: str | None = None                  # WEAK | MODERATE | STRONG | NEUTRAL
    trail_distance_pct: float | None = None  # trailing stop geri çekilme oranı
    trail_activate_pct: float | None = None  # trailing'in devreye girdiği lehte hareket
    trail_peak: float | None = None          # lehteki en uç fiyat (highwater)
    trail_active: bool = False               # trailing devreye girdi mi
    # MAE/MFE (TF-target trainer'ın yakıtı). Her tick `current_price` güncellenirken
    # _update_excursions tarafından monoton ilerletilir; kapanışta Trade'e taşınır.
    # mae_pct: entry'ye göre ters yönde gördüğü en uç hareket (pozitif %).
    # mfe_pct: entry'ye göre lehte gördüğü en uç hareket (pozitif %).
    mae_pct: float = 0.0
    mfe_pct: float = 0.0
    # F1-3 — açılış anındaki consensus modül katkı vektörü (modül → score×weight).
    # dominant_module tek-modül attribution'unun yerini alacak ham veri: kapanışta
    # Trade'e, oradan decision_log'a taşınır; learning summary attribution okur.
    # Manuel/legacy açılışlar None (consensus vektörü yok — uydurma yok).
    open_module_contributions: dict[str, float] | None = None
    # F4-3 — partial-TP shadow gözlemi (flag'ten BAĞIMSIZ her tick ilerletilir).
    # r_hit: kâr ilk kez trigger_r×|entry−SL| mesafesine değdiği an + o anki fiyat.
    # be_touched: r-hit SONRASI fiyat girişe geri döndü mü (breakeven senaryosu).
    # done: partial_tp.enabled AÇIKKEN kısmi kapatma gerçekleşti (bir kez).
    ptp_r_hit_at: str | None = None
    ptp_price_at_r: float | None = None
    ptp_be_touched: bool = False
    ptp_done: bool = False

    @property
    def unrealized_pnl_usd(self) -> float:
        # Mark-to-market is formalized in execution_sim (single source of paper P&L).
        return execution_sim.unrealized_pnl(
            self.side, self.entry_price, self.current_price, self.size_usd
        )


@dataclass
class Trade:
    id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    pnl_usd: float
    opened_at: str
    closed_at: str
    close_reason: str
    fingerprint: str | None = None
    data_verified: bool = False  # mirrors Position; learning trainer filters
    predicted_confidence: float | None = None
    raw_confidence: float | None = None
    confidence_source: str | None = None
    timeframe: str = "1d"  # T0 additive — legacy kayıtlar default "1d" yüklenir
    # P1 — terminal lifecycle + learning handoff (additive).
    lifecycle_status: str = "CLOSED"   # CLOSED (normal) | FORCE_CLOSED (zorla)
    open_reason: str | None = None
    snapshot_id: str | None = None
    # Signal attribution (additive): pozisyondan miras alınan karar izi.
    open_dqs: float | None = None
    open_risk_action: str | None = None
    # Market-session attribution (additive): pozisyondan miras alınır.
    open_session_action: str | None = None
    open_session_phase: str | None = None
    open_session_reason: str | None = None
    open_session_size_multiplier: float | None = None
    open_session_primary_market_open: bool | None = None
    open_session_evidence: str | None = None
    # MAE/MFE pozisyondan miras alınır (TF-target trainer girdisi).
    mae_pct: float = 0.0
    mfe_pct: float = 0.0
    # F1-1 — açılış risk mesafesi |entry−SL|/entry (fraksiyon; R-multiple paydası).
    # SL'siz/legacy kayıtlar None (R hesaplanamaz — uydurma yok).
    open_risk_pct: float | None = None
    # F1-3 — açılış anındaki consensus modül katkı vektörü (pozisyondan miras).
    open_module_contributions: dict[str, float] | None = None
    # F4-3 — partial-TP shadow: pozisyon 1R kârı gördü mü + görmüşse "1R'de %X
    # kapat & breakeven" stratejisinin HİPOTETİK PnL'i (yalnız r-hit'li TAM
    # kapanışlarda dolar; gerçek partial-TP uygulanan pozisyonda None — gerçek
    # leg'ler zaten ölçüm). Owner aktivasyon kanıtı: shadow vs actual toplamı.
    ptp_r_hit: bool = False
    ptp_shadow_pnl_usd: float | None = None
    # Exit-forensics — kapanan dilimin $ büyüklüğü (kısmi kapanışta realized_size).
    # Kötü çıkışın $ maliyetini kesin hesaplamak için; legacy kayıtlar None.
    size_usd: float | None = None


@dataclass
class ManualReady:
    """Owner-approval candidate (DEFENSIVE/CRISIS regime → no auto-open)."""
    id: str
    symbol: str
    timeframe: str
    side: str               # long / short
    requested_at: str
    size_multiplier: float
    requested_price: float | None = None
    reason: str | None = None
    fingerprint: str | None = None
    snapshot_id: str | None = None
    rejected_at: str | None = None  # set when owner rejected (→ silent block)


@dataclass
class RejectedSignal:
    """Owner-rejected signal — silent-blocks the same symbol+side+timeframe."""
    symbol: str
    timeframe: str
    side: str
    rejected_at: str
    fingerprint: str | None = None


@dataclass
class PendingOrder:
    """Owner bekleyen emir (limit / stop). Fiyat tetiğine gelince tick'te pozisyona
    dönüşür. PAPER_SAFE — gerçek broker emri yok."""
    id: str
    symbol: str
    side: str               # long / short
    size_usd: float
    order_type: str         # "limit" | "stop" | "stop_limit"
    trigger_price: float
    created_at: str
    timeframe: str = "1d"
    reason: str | None = None
    sl_pct: float | None = None  # opsiyonel özel stop yüzdesi
    limit_price: float | None = None  # stop_limit: tetik (trigger) sonrası dolum fiyatı


@dataclass
class PaperState:
    equity_usd: float
    peak_equity_usd: float
    realized_pnl_usd: float = 0.0
    open_positions: list[Position] = field(default_factory=list)
    recent_trades: list[Trade] = field(default_factory=list)
    daily_pnl_usd: float = 0.0
    daily_anchor_date: str = ""
    manual_ready: list[ManualReady] = field(default_factory=list)
    rejected_signals: list[RejectedSignal] = field(default_factory=list)
    pending_orders: list[PendingOrder] = field(default_factory=list)
    # Tick yan ürünü: açık pozisyon başına recheck verdict listesi (read-only öneri).
    # Boş ise henüz tick atılmamış demektir; legacy kayıtlar default boş yüklenir.
    last_rechecks: list[dict] = field(default_factory=list)
    last_recheck_at: str | None = None

    # F2-1 — mark-to-market SALT-GÖZLEM alanları. Persist edilmez (türetilir),
    # RiskGate girdisine BAĞLI DEĞİL: gate hâlâ realized `equity_usd` görür.
    # Gate'e bağlama, gözlem penceresi sonrası ayrı tarihli owner kararıdır.
    @property
    def unrealized_pnl_usd(self) -> float:
        return sum(p.unrealized_pnl_usd for p in self.open_positions)

    @property
    def mtm_equity_usd(self) -> float:
        return self.equity_usd + self.unrealized_pnl_usd

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "equity_usd": self.equity_usd,
            "peak_equity_usd": self.peak_equity_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "daily_pnl_usd": self.daily_pnl_usd,
            "daily_anchor_date": self.daily_anchor_date,
            "open_positions": [asdict(p) for p in self.open_positions],
            "recent_trades": [asdict(t) for t in self.recent_trades[-200:]],
            "manual_ready": [asdict(m) for m in self.manual_ready],
            "rejected_signals": [asdict(r) for r in self.rejected_signals],
            "pending_orders": [asdict(o) for o in self.pending_orders],
            "last_rechecks": list(self.last_rechecks),
            "last_recheck_at": self.last_recheck_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperState:
        # P1 — bilinmeyen alanları süz (forward uyumlu), eksikler default'a düşer
        # (legacy kayıtlar lifecycle/learning alanları olmadan yüklenir).
        return cls(
            equity_usd=float(d.get("equity_usd", 0)),
            peak_equity_usd=float(d.get("peak_equity_usd", 0)),
            realized_pnl_usd=float(d.get("realized_pnl_usd", 0)),
            daily_pnl_usd=float(d.get("daily_pnl_usd", 0)),
            daily_anchor_date=str(d.get("daily_anchor_date", "")),
            open_positions=[
                Position(**_only_known(Position, p))
                for p in d.get("open_positions", [])
                if isinstance(p, dict)
            ],
            recent_trades=[
                Trade(**_only_known(Trade, t))
                for t in d.get("recent_trades", [])
                if isinstance(t, dict)
            ],
            manual_ready=[
                ManualReady(**_only_known(ManualReady, m))
                for m in d.get("manual_ready", [])
                if isinstance(m, dict)
            ],
            rejected_signals=[
                RejectedSignal(**_only_known(RejectedSignal, r))
                for r in d.get("rejected_signals", [])
                if isinstance(r, dict)
            ],
            pending_orders=[
                PendingOrder(**_only_known(PendingOrder, o))
                for o in d.get("pending_orders", [])
                if isinstance(o, dict)
            ],
            last_rechecks=[
                r for r in d.get("last_rechecks", []) if isinstance(r, dict)
            ],
            last_recheck_at=d.get("last_recheck_at") or None,
        )


def _initial_state() -> PaperState:
    th = load_thresholds()["paper_trading"]
    equity = float(th["initial_equity_usd"])
    return PaperState(equity_usd=equity, peak_equity_usd=equity)


def _read_text_with_retry(path: Path) -> str:
    """state dosyasını oku; Windows'ta eşzamanlı `os.replace` dosyayı kısa süre
    kilitleyip PermissionError/OSError verebilir. Bu GEÇİCİDİR (bozulma değil),
    bu yüzden artan beklemeyle birkaç kez yeniden dener. Kalıcı kilitte son
    hatayı yükseltir — burada ASLA veri silinmez/sıfırlanmaz."""
    last: OSError | None = None
    for attempt in range(_READ_RETRIES):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:  # PermissionError dahil (WinError 5/32)
            last = exc
            time.sleep(_RETRY_BASE_SLEEP_S * (attempt + 1))
    assert last is not None  # döngü en az bir kez hata yakaladı
    raise last


def _replace_with_retry(tmp: Path, path: Path) -> None:
    """`os.replace` de aynı geçici kilide takılabilir (okuyucu dosyayı tutarken).
    Yeniden dener ki yazım sessizce düşmesin ve tmp dosyası ortada kalmasın."""
    last: OSError | None = None
    for attempt in range(_READ_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            last = exc
            time.sleep(_RETRY_BASE_SLEEP_S * (attempt + 1))
    assert last is not None
    raise last


def _write_atomic(path: Path, payload: dict) -> None:
    """Atomik yazım: temp dosya + os.replace (yarım dosya asla görünmez).

    os.replace geçici kilide takılırsa retry'lı (bkz. _replace_with_retry)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _replace_with_retry(tmp, path)


def _backup_corrupt(path: Path) -> str | None:
    """Bozuk state'i kenara al (üzerine yazma) → sonraki save temiz yazar."""
    try:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        bak = path.with_name(f"{path.stem}.corrupt-{ts}.json")
        os.replace(path, bak)
        return str(bak)
    except OSError:
        return None


def load() -> PaperState:
    global _LAST_GOOD_RAW
    with _LOCK:
        if not STATE_PATH.exists():
            state = _initial_state()
            _write_atomic(STATE_PATH, state.to_dict())
            _LAST_GOOD_RAW = state.to_dict()
            return state

        # 1) Okuma I/O'su ayrı tutulur: geçici dosya kilidi (PermissionError)
        #    BOZULMA DEĞİLDİR — retry et, asla onarım/sıfırlama tetikleme.
        try:
            raw_text = _read_text_with_retry(STATE_PATH)
        except OSError as exc:
            # B2 — kalıcı kilit (retry'lar tükendi; pratikte ~hiç olmaz). Disk
            # dosyasına DOKUNMA: yedekleme/sıfırlama YOK → gerçek veri yerinde
            # kalır, sıradaki başarılı load onu okur. Süreç-içi son-iyi varsa onu
            # döndür (read-modify-write'ın boş default'la ezmesini önler).
            audit.record(
                "STATE_READ_LOCKED",
                reason=f"transient_lock:{type(exc).__name__}",
            )
            if _LAST_GOOD_RAW is not None:
                return PaperState.from_dict(_LAST_GOOD_RAW)
            return _initial_state()

        # 2) Parse: yalnız GERÇEK bozulma (JSON parse edilemiyor / şema bozuk)
        #    onarımı tetikler. PermissionError artık buraya DÜŞMEZ.
        try:
            raw = json.loads(raw_text)
            state = PaperState.from_dict(raw)
            _LAST_GOOD_RAW = raw
            return state
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            # P1 — corrupt state: yedekle + temiz default yaz (crash YOK).
            bak = _backup_corrupt(STATE_PATH)
            state = _initial_state()
            try:
                _write_atomic(STATE_PATH, state.to_dict())
            except OSError:
                pass
            audit.record(
                "STATE_REPAIRED",
                reason=f"corrupt_paper_state:{type(exc).__name__}",
                backup=bak,
            )
            _LAST_GOOD_RAW = state.to_dict()
            return state


def save(state: PaperState) -> None:
    with _LOCK:
        _write_atomic(STATE_PATH, state.to_dict())


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()
