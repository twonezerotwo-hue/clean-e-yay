"""GET/POST /api/v1/agent-mode/config — Agent Mode Control (spec §5/§40).

Owner'ın profil (SCALP/INTRADAY/TACTICAL/SWING/POSITION) ve strateji
(reversal/trend/range/breakout) izinlerini dashboard'dan ayarlamasını sağlar.
Yazım `packages/mode/store.py`'a (file-backed override) gider — ana thresholds
dosyası ASLA yazılmaz. Bu filtre şu an conflict_resolver/shadow gözleminde
okunur; live decide_matrix auto-open'ı DEĞİŞTİRMEZ (Faz 4'e kadar).
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.mode import config as mode_config
from packages.mode import store as mode_store

router = APIRouter(tags=["agent-mode"])

# Bu filtrenin şu an karar zincirindeki gerçek etki alanı (dürüst etiket; UI
# kullanıcıya "live auto-open'ı değiştirmez" mesajını bundan gösterir).
APPLIES_TO = "shadow_conflict_observation"


def _config_values(cfg: mode_config.AgentModeConfig) -> dict:
    return {
        "enabled_trade_profiles": list(cfg.enabled_trade_profiles),
        "disabled_trade_profiles": list(cfg.disabled_trade_profiles),
        "focus_mode": cfg.focus_mode,
        "allow_counter_context_trades": cfg.allow_counter_context_trades,
        "allow_reversal_trades": cfg.allow_reversal_trades,
        "allow_trend_follow_trades": cfg.allow_trend_follow_trades,
        "allow_range_trades": cfg.allow_range_trades,
        "allow_breakout_trades": cfg.allow_breakout_trades,
        "watch_disabled_profiles": cfg.watch_disabled_profiles,
        "close_disabled_profile_positions": cfg.close_disabled_profile_positions,
        "close_requires_riskgate_pass": cfg.close_requires_riskgate_pass,
    }


def _view() -> dict:
    cfg = mode_config.load_config()
    return {
        "trade_profiles": list(mode_config.TRADE_PROFILES),
        "config": _config_values(cfg),
        "overrides": mode_store.load_overrides(),
        "applies_to": APPLIES_TO,
    }


@router.get("/agent-mode/config")
def get_agent_mode_config() -> dict:
    """Etkin Agent Mode config'i (thresholds defaults + owner override) + profil
    listesi + ham override'lar. Read-only görüntü."""
    return _view()


@router.post("/agent-mode/config")
def post_agent_mode_config(payload: dict) -> dict:
    """Owner override'larını kaydet (sanitize edilir; bilinmeyen anahtar/profil
    reddedilir). Ana thresholds dosyasına dokunmaz. Etkin config'i geri döner."""
    mode_store.save_overrides(payload or {})
    return _view()


@router.post("/agent-mode/config/reset")
def post_agent_mode_config_reset() -> dict:
    """Tüm override'ları sil → saf thresholds config'e dön."""
    mode_store.clear()
    return _view()
