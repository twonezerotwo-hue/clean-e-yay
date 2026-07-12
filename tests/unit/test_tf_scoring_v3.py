"""tf_scoring_v3 testleri — v2 çekirdeği + bayat-karne kapısı + makro-kararlılık.

Backtest kanıtı (2026-07-12): makro-UYUM kısması çürüdü (kurulmadı);
makro-KARARLILIK kısması hafif pozitif (+0.729 vs v2 +0.686) → v3 kuralı bu.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.scoring import tf_scoring_v3 as v3


def _fresh_scorecard(days_old=0.0):
    gen = datetime.now(UTC) - timedelta(days=days_old)
    return {"generated_at": gen.isoformat()}


def test_macro_decisive_band():
    assert v3.macro_decisive(65.0) is True     # risk-on kararlı
    assert v3.macro_decisive(35.0) is True     # risk-off kararlı
    assert v3.macro_decisive(55.0) is False    # bant içi → kararsız
    assert v3.macro_decisive(None) is False    # skor yok → kararsız (uydurma yok)


def test_macro_damp_never_boosts_never_flips():
    assert v3.macro_damp(0.8, True) == 0.8            # kararlı → dokunma
    assert v3.macro_damp(0.8, False) == 0.4           # kararsız → kısılır
    assert v3.macro_damp(-0.6, False) == -0.3         # işaret KORUNUR
    assert v3.macro_damp(None, False) is None


def test_stale_scorecard_silences_v3():
    """Yarış dersi: bayat karneyle çağrı yapılmaz (59/59 kaybın kök nedeni)."""
    tf_scores = {"1d": 0.5, "4h": 0.4}
    fresh = v3.score(tf_scores, "UP", rotation_score=70.0,
                     scorecard=_fresh_scorecard(2.0))
    stale = v3.score(tf_scores, "UP", rotation_score=70.0,
                     scorecard=_fresh_scorecard(15.0))
    assert fresh == 0.5      # taze + UP → 1d konuşur, makro kararlı → tam
    assert stale is None     # bayat → sessizlik
    assert v3.score(tf_scores, "UP", rotation_score=70.0, scorecard={}) is None


def test_score_pipeline_regime_and_damp():
    tf_scores = {"1d": 0.5, "4h": -0.4}
    # DOWN → 4h konuşur; makro kararsız (50) → yarıya kısılır
    s = v3.score(tf_scores, "DOWN", rotation_score=50.0,
                 scorecard=_fresh_scorecard())
    assert s == -0.2
    # konuşmacı TF kanıtsız → None (vekâlet yok — v2 kuralı aynen)
    assert v3.score({"1d": 0.5}, "DOWN", rotation_score=70.0,
                    scorecard=_fresh_scorecard()) is None
    # rejim bilinmiyor → None
    assert v3.score(tf_scores, None, rotation_score=70.0,
                    scorecard=_fresh_scorecard()) is None
