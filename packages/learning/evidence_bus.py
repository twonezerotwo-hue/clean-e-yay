"""I1 — Kanıt Otobüsü (Evidence Bus): tüm öğrenme ölçümlerini TEK normalize
şemaya toplar (salt-gözlem).

Amaç (owner talebi 2026-07-05, `docs/LEARNING_INTEGRATION_REPORT.md`): 40+
öğrenici bugün ayrı dosya/panele yazıyor → "sistem şu an neyi biliyor?" sorusu
dağınık. Bu otobüs mevcut ölçümleri (signal_quality/edge/quantum karnesi/keşif
gölge karnesi/tf-kalibrasyon) TEK `EvidenceRecord` listesine indirger. Böylece
tek sorgu = tüm kanıt; bir öğrenici başka bir öğrenicinin kanıtını okuyabilir
(I2 olgunluk kapısı + I3 kaynak seçici bunun üstüne kurulur).

PAZARLIKSIZ: SALT-GÖZLEM. Mevcut fonksiyonları/artifact'ları OKUR; hiçbir şey
üretmez/değiştirmez/karara bağlamaz. Her kaynak İZOLE (biri patlarsa otobüs
düşmez — worker deseni). Kaynak damgası (`source: live|shadow|backtest`) I3'ün
temeli: canlı mı, gölge mi, backtest mi kanıt olduğu her zaman görünür.

PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from packages.learning import maturity_gate

# Kaynak sınıfları (I3 kaynak seçicinin temeli).
LIVE = "live"          # canlı paper outcome'larından
SHADOW = "shadow"      # gölge kanallardan (keşif/missed-opp)
BACKTEST = "backtest"  # geçmiş-prova (challenger) kayıtlarından


@dataclass
class EvidenceRecord:
    """Bir ölçümün normalize kaydı — her öğrenme kanıtı bu şekle iner."""

    topic: str                       # signal_quality / quantum_discrimination / edge_stability / ...
    subject: str                     # ölçülen şey (touche@NEUTRAL / quantum@DEFENSIVE / XLV / 4h)
    source: str                      # live | shadow | backtest
    regime: str | None = None
    timeframe: str | None = None
    n_samples: int | None = None     # kanıtın örneklem büyüklüğü (olgunluğun girdisi — I2)
    statistic: float | None = None   # ana sayı (ayrım / cf_win_rate / expectancy / yoğunlaşma)
    verdict: str | None = None       # DISCRIMINATES / STABLE / CALIBRATED / RESOLVED / ...
    maturity: dict | None = None     # I2 olgunluk damgası (level 0-3 + reason); collect() doldurur
    detail: dict = field(default_factory=dict)


# ------------------------------------------------------------ kaynak adaptörleri

def _signal_quality_records() -> list[EvidenceRecord]:
    """FAZ-4 sinyal kalitesi (CANLI outcome'lar): modül×rejim ayrım karnesi."""
    from packages.learning import outcomes as om
    from packages.learning import signal_quality as sq
    from packages.paper import state as ps

    card = sq.regime_module_scorecard(om.outcomes_from_state(ps.load()))
    out: list[EvidenceRecord] = []
    for regime, mods in (card.get("per_regime") or {}).items():
        for module, d in mods.items():
            nw, nl = int(d.get("n_win") or 0), int(d.get("n_loss") or 0)
            out.append(EvidenceRecord(
                topic="signal_quality", subject=f"{module}@{regime}", source=LIVE,
                regime=regime, n_samples=nw + nl,
                statistic=d.get("rel_separation"), verdict=d.get("verdict"),
                detail={"n_win": nw, "n_loss": nl, "separation": d.get("separation")},
            ))
    return out


def _quantum_records() -> list[EvidenceRecord]:
    """Quantum ayrım karnesi (BACKTEST challenger): rejim başına DISCRIMINATES/…"""
    from packages.learning import challenger_trainer as ct

    vm = ct.viewmodel()
    if not vm.get("enabled"):
        return []
    return [
        EvidenceRecord(
            topic="quantum_discrimination", subject=f"quantum@{q.get('regime')}",
            source=BACKTEST, regime=q.get("regime"), n_samples=q.get("n"),
            statistic=q.get("separation"), verdict=q.get("verdict"),
            detail={"correlation": q.get("correlation")},
        )
        for q in (vm.get("quantum") or [])
    ]


def _edge_records() -> list[EvidenceRecord]:
    """Edge stabilitesi (CANLI): otomatik-ayara güvenli mi (safe_to_autotune)."""
    from packages.learning import edge_report

    r = edge_report.report()
    return [EvidenceRecord(
        topic="edge_stability", subject="global", source=LIVE,
        n_samples=r.get("total"), statistic=r.get("outlier_concentration"),
        verdict=r.get("verdict"),
        detail={
            "safe_to_autotune": r.get("safe_to_autotune"),
            "outlier_dependent": r.get("outlier_dependent"),
        },
    )]


def _discovery_records() -> list[EvidenceRecord]:
    """Keşif adayları (SHADOW): aday başına çözülmüş isabet karnesi."""
    from packages.discovery import shadow_ledger

    cs = shadow_ledger.candidate_summary()
    out: list[EvidenceRecord] = []
    for sym, d in (cs.get("candidates") or {}).items():
        decisive = int(d.get("missed_win") or 0) + int(d.get("avoided_loss") or 0)
        out.append(EvidenceRecord(
            topic="discovery_candidate", subject=str(sym), source=SHADOW,
            n_samples=decisive, statistic=d.get("cf_win_rate"),
            verdict="RESOLVED" if decisive else "PENDING",
            detail={"timeframes": d.get("timeframes"), "resolved": d.get("resolved")},
        ))
    return out


def _regime_brake_records() -> list[EvidenceRecord]:
    """Rejim risk freni (Y-1, çift kanıt): rejim başına fren hükmü.

    Yalnız kanıtlı satırlar (iki kaynaktan en az biri örnek görmüş) — boş rejim
    otobüsü şişirmez. Kaynak damgası LIVE: fren kararının bağlayıcı yarısı canlı
    kohorttur (backtest yarısı detail'de yan yana)."""
    from packages.learning import regime_risk_brake

    vm = regime_risk_brake.viewmodel()
    out: list[EvidenceRecord] = []
    for reg, row in (vm.get("per_regime") or {}).items():
        ev = row.get("evidence") or {}
        live_n = int(((ev.get("live") or {}).get("n")) or 0)
        bt_n = int(((ev.get("backtest") or {}).get("n")) or 0)
        if not live_n and not bt_n:
            continue
        out.append(EvidenceRecord(
            topic="regime_risk_brake", subject=f"size@{reg}", source=LIVE,
            regime=reg, n_samples=live_n,
            statistic=(ev.get("live") or {}).get("pnl_usd"),
            verdict="BRAKED" if row.get("braked") else "NO_BRAKE",
            detail={"mult": row.get("mult"), "enabled": vm.get("enabled"),
                    "backtest": ev.get("backtest"), "live": ev.get("live")},
        ))
    return out


def _meta_gate_records() -> list[EvidenceRecord]:
    """Meta-label kapısı (Y-5, SALT-GÖLGE): dominant×TF kovası bariyer-kalite.

    Kaynak damgası SHADOW — kapının hükmü karara/boyuta uygulanmaz (aktivasyon
    ayrı dilim + owner). Yalnız min_bucket_n eşiğini geçen kovalar (kanıtsız kova
    otobüsü şişirmez). statistic = quality_score ∈ [−1,+1]."""
    from packages.learning import meta_gate

    vm = meta_gate.viewmodel()
    min_n = int((vm.get("config") or {}).get("min_bucket_n") or 0)
    out: list[EvidenceRecord] = []
    for key, b in (vm.get("buckets") or {}).items():
        n = int(b.get("n") or 0)
        if n < min_n:
            continue
        module, _, tf = str(key).partition("|")
        out.append(EvidenceRecord(
            topic="meta_gate", subject=key, source=SHADOW,
            timeframe=tf or None, n_samples=n,
            statistic=b.get("quality_score"),
            verdict="GOOD" if float(b.get("quality_score") or 0.0) > 0 else "WEAK",
            detail={"module": module, "good": b.get("good"), "bad": b.get("bad"),
                    "quality": b.get("quality")},
        ))
    return out


def _tf_calibration_records() -> list[EvidenceRecord]:
    """TF kalibrasyonu (CANLI): TF başına güven (CALIBRATED/PRIOR) + expectancy."""
    from packages.learning import tf_calibration

    r = tf_calibration.calibration_report()
    return [
        EvidenceRecord(
            topic="tf_calibration", subject=str(c.get("timeframe")), source=LIVE,
            timeframe=c.get("timeframe"), n_samples=c.get("trades"),
            statistic=c.get("expectancy"), verdict=c.get("trust"),
        )
        for c in (r.get("per_timeframe") or [])
    ]


# Kayıtlı kaynak adaptörleri (yeni öğrenici eklendikçe buraya bir satır).
_SOURCES = (
    _signal_quality_records,
    _quantum_records,
    _edge_records,
    _discovery_records,
    _tf_calibration_records,
    _regime_brake_records,
    _meta_gate_records,
)


def _global_edge_safe(records: list[EvidenceRecord]) -> bool | None:
    """Sistemin GLOBAL edge stabilitesi (edge_stability kaydından). I2 kapısı
    her kaydın basamak-3 (oto) uygunluğunu buna göre değerlendirir."""
    for r in records:
        if r.topic == "edge_stability":
            val = (r.detail or {}).get("safe_to_autotune")
            if isinstance(val, bool):
                return val
    return None


def collect() -> list[EvidenceRecord]:
    """Tüm kaynakları tek normalize kanıt listesine topla + I2 olgunluk damgası
    (salt-gözlem).

    Her kaynak İZOLE try içinde: biri patlarsa atlanır, otobüs asla düşmez
    (worker deseni). Toplama sonrası her kayda `maturity` eklenir (global edge
    stabilitesiyle) — kanıtın ne kadar olgun olduğu tek yerde görünür."""
    out: list[EvidenceRecord] = []
    for source_fn in _SOURCES:
        try:
            out.extend(source_fn())
        except Exception:  # defensive — bir kaynak otobüsü düşürmez
            continue
    edge_safe = _global_edge_safe(out)
    for r in out:
        try:
            r.maturity = maturity_gate.assess(
                n_samples=r.n_samples, verdict=r.verdict, edge_safe=edge_safe
            )
        except Exception:  # defensive — damga hatası otobüsü düşürmez
            r.maturity = None
    return out


def viewmodel() -> dict:
    """`GET /learning/evidence-bus` görünümü: tüm kanıt + kaynak/konu/hüküm sayacı."""
    records = collect()
    by_source: dict[str, int] = {}
    by_topic: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    by_maturity: dict[str, int] = {}
    for r in records:
        by_source[r.source] = by_source.get(r.source, 0) + 1
        by_topic[r.topic] = by_topic.get(r.topic, 0) + 1
        key = r.verdict or "—"
        by_verdict[key] = by_verdict.get(key, 0) + 1
        mkey = (r.maturity or {}).get("maturity") or "—"
        by_maturity[mkey] = by_maturity.get(mkey, 0) + 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(records),
        "by_source": by_source,
        "by_topic": by_topic,
        "by_verdict": by_verdict,
        "by_maturity": by_maturity,
        "records": [asdict(r) for r in records],
        "note": (
            "salt-gözlem; tüm öğrenme ölçümlerinin tek normalize görünümü (I1). "
            "kaynak: live=canlı paper, shadow=gölge kanal, backtest=geçmiş-prova."
        ),
    }


__all__ = ["BACKTEST", "LIVE", "SHADOW", "EvidenceRecord", "collect", "viewmodel"]
