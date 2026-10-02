"""Golden replay — canlı konfigürasyonla karar matrisinin dondurulmuş çıktısı.

Temizlik protokolünün güvenlik ağı (bkz. temizlik raporu, Bölüm 1 madde 2).
Unit testler conftest'te canlı flag'lerin çoğunu KAPALIYA pinler; bu araç ise
`config/` altındaki GERÇEK canlı eşik/flag setiyle `decide_matrix`'i koşar ve
çıktıyı JSON olarak dondurur. Davranışı değiştirmemesi gereken her PR bu
çıktıyı bayt-aynı üretmek zorundadır.

İzolasyon:
- Fixture veri (`TEST_USE_MOCK=true`), ağ yok, LLM kapalı.
- Tüm runtime yolları geçici bir dizine yönlendirilir; makinedeki
  `data/runtime` (oto-uygulanmış ağırlık, eşik override'ı, kalibrasyon vb.)
  OKUNMAZ. Böylece sonuç yalnız repodaki kod + config'e bağlıdır.
- Saat sabitlenir (FROZEN_NOW); fixture barları ve tazelik kontrolleri ona göre.

Kullanım:
    python -m tests.golden.golden_replay --write   # golden dosyayı yeniden üret
    python -m tests.golden.golden_replay --check   # farkı göster, fark varsa exit 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time as _time_mod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN_PATH = Path(__file__).resolve().parent / "decisions_live.json"
FROZEN_NOW = datetime(2026, 9, 15, 13, 7, 0, tzinfo=UTC)  # Salı, ABD seansı açık

# Runtime yolu taşıyan env'ler + davranışı makineye göre değiştiren flag'ler.
_PATH_SUFFIXES = ("_PATH", "_DIR")
_FLAG_ENVS_TO_CLEAR = (
    "THRESHOLD_AUTOTUNE",
    "REBALANCE_AUTO_APPLY",
    "TF_CALIBRATION_AUTO_ONLY",
    "TF_TARGET_AUTO_ONLY",
    "TF_TARGET_TRAIL_AUTOTUNE",
    "TF_TARGET_EDGE_GATE",
    "TF_TRUST_PER_BUCKET",
    "WEIGHT_LOSS_AWARE",
    "LEARNING_ADVISOR_APPLY",
    "MISTAKE_MEMORY_V2",
    "EXIT_FORENSICS_NUDGE",
    "DISCOVERY_SCAN_ENABLED",
    "PRICE_USE_MOCK",
)

# (ad, RiskInput alanları, açık pozisyon var mı, paper_exploration)
SCENARIOS: list[tuple[str, dict, bool]] = [
    ("normal", {"dqs_score": 90.0, "equity_usd": 100_000.0, "peak_equity_usd": 100_000.0,
                "daily_pnl_usd": 0.0, "open_position_count": 0}, False),
    ("normal_exploration", {"dqs_score": 90.0, "equity_usd": 100_000.0,
                            "peak_equity_usd": 100_000.0, "daily_pnl_usd": 0.0,
                            "open_position_count": 0}, True),
    ("daily_loss_breach", {"dqs_score": 90.0, "equity_usd": 97_500.0,
                           "peak_equity_usd": 100_000.0, "daily_pnl_usd": -2_500.0,
                           "open_position_count": 0}, False),
    ("max_dd_breach", {"dqs_score": 90.0, "equity_usd": 91_000.0,
                       "peak_equity_usd": 100_000.0, "daily_pnl_usd": 0.0,
                       "open_position_count": 0}, False),
    ("dqs_low", {"dqs_score": 40.0, "equity_usd": 100_000.0, "peak_equity_usd": 100_000.0,
                 "daily_pnl_usd": 0.0, "open_position_count": 0}, False),
]


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return FROZEN_NOW if tz is not None else FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def utcnow(cls):  # type: ignore[override]
        return FROZEN_NOW.replace(tzinfo=None)


class _FrozenTime:
    """`time` modülü vekili: yalnız `time()` donuk, gerisi gerçek modüle gider."""

    def __getattr__(self, name: str):
        return getattr(_time_mod, name)

    @staticmethod
    def time() -> float:
        return FROZEN_NOW.timestamp()


@contextmanager
def isolated_runtime() -> Iterator[Path]:
    """Env + saat izolasyonu; çıkışta her şey eski hâline döner."""
    saved_env = dict(os.environ)
    tmp = Path(tempfile.mkdtemp(prefix="golden-replay-"))
    try:
        for key in list(os.environ):
            # Yol env'leri + API anahtarları: makine durumu ve ağ dışarıda kalır.
            if key.endswith(_PATH_SUFFIXES) or key.endswith("_API_KEY"):
                del os.environ[key]
        for key in _FLAG_ENVS_TO_CLEAR:
            os.environ.pop(key, None)
        os.environ["TEST_USE_MOCK"] = "true"
        os.environ["LLM_MODE"] = "off"
        os.environ["LLM_LOAD_DOTENV"] = "false"
        os.environ["TAVILY_LOAD_DOTENV"] = "false"
        os.environ["API_AUTH_TOKEN"] = ""
        rt = tmp / "runtime"
        rt.mkdir()
        # Bilinen tüm *_PATH env'lerini geçici dizine yönlendir.
        names = (
            "SNAPSHOT_STORE_PATH PAPER_STATE_PATH PAPER_AUDIT_PATH DECISION_LOG_PATH "
            "RISK_HALT_PATH WORKER_HEARTBEAT_PATH LEARNING_RUN_PATH LEARNING_OUT_PATH "
            "CALIBRATION_STORE_PATH REBALANCE_STORE_PATH LLM_BUDGET_PATH LLM_CACHE_PATH "
            "EMPIRICAL_PWIN_PATH META_GATE_PATH META_GATE_SHADOW_PATH MISSED_OPP_LOG_PATH "
            "NOTIFICATIONS_PATH REGIME_RISK_BRAKE_PATH REGIME_STATE_PATH SHADOW_LOG_PATH "
            "TF_CALIBRATION_OUT_PATH TF_SCORING_V2_SHADOW_PATH TF_TARGET_STORE_PATH "
            "TF_TARGET_AUTOAPPLY_PATH THRESHOLD_OVERRIDES_PATH THRESHOLD_AUTOAPPLY_PATH "
            "GUARD_OVERRIDES_PATH GUARD_MONITOR_STORE_PATH WEIGHT_AUTOAPPLY_PATH "
            "CUSTOM_ASSETS_PATH AGENT_MODE_STORE_PATH CALIBRATION_AUDIT_PATH "
            "ZONE_VERDICTS_PATH TICKETS_PATH"
        ).split()
        for n in names:
            os.environ[n] = str(rt / f"{n.lower()}.json")
        os.environ["OHLCV_CACHE_DIR"] = str(rt / "ohlcv")
        os.environ["WEIGHTS_OUTPUT_DIR"] = str(rt / "weights")
        os.environ["WEIGHTS_MANIFEST_PATH"] = str(rt / "weights_manifest.json")
        yield rt
    finally:
        os.environ.clear()
        os.environ.update(saved_env)


def _freeze_clock() -> list[tuple[object, str, object]]:
    """Paket modüllerindeki `datetime` adını donmuş sınıfla değiştir (geri alınabilir)."""
    patched: list[tuple[object, str, object]] = []
    for name, mod in list(sys.modules.items()):
        if not (name.startswith("packages.") or name.startswith("apps.")) or mod is None:
            continue
        if getattr(mod, "datetime", None) is datetime:
            patched.append((mod, "datetime", datetime))
            mod.datetime = _FrozenDatetime  # type: ignore[attr-defined]
        if getattr(mod, "time", None) is _time_mod:
            patched.append((mod, "time", _time_mod))
            mod.time = _FrozenTime()  # type: ignore[attr-defined]
    return patched


def _unfreeze(patched: list[tuple[object, str, object]]) -> None:
    for mod, attr, orig in patched:
        setattr(mod, attr, orig)


def _r(x: object) -> object:
    return round(x, 6) if isinstance(x, float) else x


def _row(d) -> dict:
    return {
        "symbol": d.symbol,
        "timeframe": d.timeframe,
        "action": d.action,
        "candidate_action": d.candidate_action,
        "confidence": _r(d.confidence),
        "raw_confidence": _r(d.raw_confidence),
        "confidence_source": d.confidence_source,
        "size_multiplier": _r(d.size_multiplier),
        "expected_value": _r(d.expected_value),
        "blocked_by": list(d.blocked_by),
        "fingerprint": d.fingerprint,
        "risk_action": d.risk.action,
        "consensus_score": _r(d.consensus.score),
        "reason": d.reason,
    }


def run() -> dict:
    """Tüm senaryoları koş, deterministik sözlük döndür."""
    with isolated_runtime():
        # Import'lar izolasyon kurulduktan SONRA (modül-seviyesi yol sabitleri için).
        from packages.data.ingestion.pipeline import build_snapshot
        from packages.data.registry import assets as asset_registry
        from packages.data.registry import loader
        from packages.decision import engine
        from packages.decision.engine import decide_matrix
        from packages.risk.engine import RiskInput

        loader.WEIGHTS_RUNTIME_DIR = Path(os.environ["WEIGHTS_OUTPUT_DIR"])  # type: ignore[attr-defined]
        patched = _freeze_clock()
        try:
            symbols = asset_registry.trade_symbols()
            snap = build_snapshot()
            out: dict = {
                "frozen_now": FROZEN_NOW.isoformat(),
                "symbols": symbols,
                "dqs": _r(snap.quality.score),
                "scenarios": {},
            }
            for name, risk_kwargs, exploration in SCENARIOS:
                regime, risk, decisions = decide_matrix(
                    symbols,
                    snap,
                    RiskInput(**risk_kwargs),
                    open_positions=[],
                    paper_exploration=exploration,
                )
                out["scenarios"][name] = {
                    "regime": regime.label,
                    "risk_action": risk.action,
                    "decisions": sorted(
                        (_row(d) for d in decisions),
                        key=lambda r: (r["symbol"], r["timeframe"]),
                    ),
                }
            _ = engine  # modül yüklendi (saat yaması kapsamı için)
            return out
        finally:
            _unfreeze(patched)


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def diff(old: dict, new: dict) -> list[str]:
    lines: list[str] = []
    for key in ("frozen_now", "symbols", "dqs"):
        if old.get(key) != new.get(key):
            lines.append(f"{key}: {old.get(key)!r} -> {new.get(key)!r}")
    for sc in sorted(set(old.get("scenarios", {})) | set(new.get("scenarios", {}))):
        o = old.get("scenarios", {}).get(sc)
        n = new.get("scenarios", {}).get(sc)
        if o is None or n is None:
            lines.append(f"[{sc}] senaryo {'eklendi' if o is None else 'silindi'}")
            continue
        for k in ("regime", "risk_action"):
            if o[k] != n[k]:
                lines.append(f"[{sc}] {k}: {o[k]} -> {n[k]}")
        od = {(r["symbol"], r["timeframe"]): r for r in o["decisions"]}
        nd = {(r["symbol"], r["timeframe"]): r for r in n["decisions"]}
        for cell in sorted(set(od) | set(nd)):
            a, b = od.get(cell), nd.get(cell)
            if a != b:
                if a is None or b is None:
                    lines.append(f"[{sc}] {cell}: hücre {'eklendi' if a is None else 'silindi'}")
                    continue
                for f in sorted(set(a) | set(b)):
                    if a.get(f) != b.get(f):
                        lines.append(f"[{sc}] {cell[0]}/{cell[1]} {f}: {a.get(f)!r} -> {b.get(f)!r}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="golden dosyayı yeniden üret")
    g.add_argument("--check", action="store_true", help="golden ile karşılaştır")
    args = ap.parse_args(argv)
    data = run()
    if args.write:
        GOLDEN_PATH.write_text(dumps(data), encoding="utf-8")
        n = sum(len(s["decisions"]) for s in data["scenarios"].values())
        print(f"golden yazıldı: {GOLDEN_PATH.relative_to(REPO)} ({n} karar)")
        return 0
    old = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    lines = diff(old, data)
    if not lines:
        print("golden replay: BAYT-AYNI")
        return 0
    print(f"golden replay: {len(lines)} fark")
    for line in lines[:200]:
        print("  " + line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
