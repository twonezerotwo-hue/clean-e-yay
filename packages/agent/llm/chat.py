"""State-grounded chat — kullanıcı sorularını mevcut backend state'iyle yanıtlar.

Akış: injection guard → deterministik grounded yanıt (her zaman üretilir)
→ LLM varsa aynı bağlamla daha akıcı anlatım. LLM yoksa/başarısızsa
deterministik yanıt döner; state'te olmayan şey UYDURULMAZ.
"""
from __future__ import annotations

import hashlib

from packages.agent.llm import budget, cache, guard
from packages.agent.llm import client as llm_client
from packages.agent.llm import context as ctx_mod

_SYMBOL_ALIASES = {
    "btc": "BTCUSD",
    "bitcoin": "BTCUSD",
    "eth": "ETHUSD",
    "ethereum": "ETHUSD",
    "xau": "XAUUSD",
    "altın": "XAUUSD",
    "gold": "XAUUSD",
    "xag": "XAGUSD",
    "gümüş": "XAGUSD",
    "silver": "XAGUSD",
}

_TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")


def _detect_symbol(folded: str) -> str | None:
    for alias, sym in _SYMBOL_ALIASES.items():
        if alias in folded:
            return sym
    return None


def _detect_timeframe(folded: str) -> str | None:
    for tf in _TIMEFRAMES:
        if tf in folded:
            return tf
    return None


def _cells_for(ctx: dict, symbol: str, timeframe: str | None) -> list[dict]:
    cells = ctx["matrix"]["top_cells"] + ctx["matrix"]["candidate_vs_final_diffs"]
    # top_cells ve diffs farklı şekilli — normalize et (symbol/timeframe/final/blocked_by).
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for c in cells:
        key = (c["symbol"], c["timeframe"])
        if c["symbol"] != symbol or key in seen:
            continue
        if timeframe and c["timeframe"] != timeframe:
            continue
        seen.add(key)
        out.append(c)
    return out


def _fmt_cell(c: dict) -> str:
    blocked = ", ".join(c.get("blocked_by") or [])
    final = c.get("final", c.get("action", "?"))
    cand = c.get("candidate", "?")
    base = f"{c['symbol']} {c['timeframe']}: aday {cand} → final {final}"
    if blocked:
        base += f" (blocked_by: {blocked})"
    elif c.get("reason"):
        base += f" ({c['reason']})"
    return base


def _suspended_note(ctx: dict) -> str | None:
    if not ctx_mod.no_actionable_decision(ctx):
        return None
    rg = ctx["matrix"]["risk_gate"] or {}
    if ctx["dqs"]["status"] == "BLOCKED":
        return (
            f"Şu an aksiyon alınamaz: DQS BLOCKED (skor {ctx['dqs']['score']:.0f}) — "
            "doğrulanmış veri yetersiz, yeni karar üretilmiyor."
        )
    return (
        f"Şu an aksiyon alınamaz: risk gate kısıtlayıcı ({rg.get('action')} — "
        f"{rg.get('reason')})."
    )


def _missing_data_answer(ctx: dict) -> tuple[str, list[str]]:
    missing: list[str] = []
    for name, meta in (ctx.get("provider_issues") or {}).items():
        missing.append(f"{name}: {meta.get('status', 'sorunlu')}")
    missing += list(ctx["dqs"]["notes"])
    missing += [w for w in ctx.get("warnings") or [] if "DEGRADED" in w]
    if not missing:
        return (
            "State'e göre kritik veri eksiği görünmüyor; tüm sağlayıcılar OK.",
            [f"dqs:{ctx['dqs']['status']}"],
        )
    listing = "; ".join(missing[:6])
    return (
        f"Eksik/sorunlu veri: {listing}. DQS {ctx['dqs']['status']} "
        f"({ctx['dqs']['score']:.0f}).",
        [f"missing:{m}" for m in missing[:6]],
    )


def _risk_gate_answer(ctx: dict) -> tuple[str, list[str]]:
    rg = ctx["matrix"]["risk_gate"] or {}
    parts = [f"RiskGate: {rg.get('action')} — {rg.get('reason')}."]
    evidence = [f"risk_gate:{rg.get('action')}"]
    if ctx["halt"]["active"]:
        halts = ", ".join(f"{h['type']}→{h['level']}" for h in ctx["halt"]["events"])
        parts.append(f"Aktif halt: {halts} (sadece owner reset kapatır).")
        evidence += [f"halt:{h['type']}" for h in ctx["halt"]["events"]]
    blocked = ctx["matrix"]["blocked_by_reasons"]
    if blocked:
        parts.append("Hücreleri kesen kapılar: " + ", ".join(blocked[:5]) + ".")
        evidence += [f"blocked_by:{b}" for b in blocked[:5]]
    return " ".join(parts), evidence


def _why_no_trade_answer(ctx: dict, symbol: str, timeframe: str | None) -> tuple[str, list[str]]:
    note = _suspended_note(ctx)
    cells = _cells_for(ctx, symbol, timeframe)
    if note:
        return (
            f"{symbol} için pozisyon açılmadı çünkü {note}",
            [f"dqs:{ctx['dqs']['status']}", "matrix:suspended"],
        )
    if not cells:
        # diff yoksa sembol matrix evreninde mi?
        if symbol not in (ctx["matrix"]["symbols"] or []):
            return (
                f"{symbol} decision matrix evreninde değil — bu sembol için "
                "state'te karar verisi yok.",
                ["matrix:symbols"],
            )
        return (
            f"{symbol} için gate'lerce kesilen bir aday yok: consensus eşiği "
            "aşılmadı (yön sinyali zayıf) ya da hücre zaten actionable.",
            [f"matrix:{symbol}"],
        )
    lines = [_fmt_cell(c) for c in cells[:5]]
    return (
        f"{symbol} kararının gerekçesi hücre bazında: " + " | ".join(lines),
        [f"matrix:{_fmt_cell(c)}" for c in cells[:5]],
    )


def _waiting_answer(ctx: dict) -> tuple[str, list[str]]:
    note = _suspended_note(ctx)
    if note:
        missing, _ = _missing_data_answer(ctx)
        return (
            f"{note} Agent'ın beklediği şey: kısıtların kalkması. {missing}",
            [f"dqs:{ctx['dqs']['status']}"],
        )
    actions = ctx["matrix"]["paper_actions"]
    if actions:
        acts = ", ".join(
            f"{a['symbol']} {a['timeframe']} {a['paper_action']}" for a in actions[:4]
        )
        return (
            f"Agent beklemede değil — actionable hücreler var: {acts}. "
            "Paper tick'te RiskGate onayıyla uygulanır.",
            [f"paper_action:{a['symbol']}:{a['timeframe']}" for a in actions[:4]],
        )
    diffs = ctx["matrix"]["candidate_vs_final_diffs"]
    if diffs:
        lines = " | ".join(_fmt_cell(d) for d in diffs[:3])
        return (
            f"Agent izleme modunda: adaylar var ama gate'ler kesiyor — {lines}. "
            "Bu blokların temizlenmesini bekliyor.",
            [f"matrix:{_fmt_cell(d)}" for d in diffs[:3]],
        )
    return (
        "Agent izleme modunda: hiçbir hücrede consensus eşiği aşılmış aday yok; "
        "daha güçlü sinyal bekleniyor.",
        [f"regime:{ctx['matrix']['regime']}"],
    )


def _overview_answer(ctx: dict) -> tuple[str, list[str]]:
    m = ctx["matrix"]
    rg = m["risk_gate"] or {}
    note = _suspended_note(ctx)
    parts = [
        f"Rejim {m['regime']}, DQS {ctx['dqs']['status']} ({ctx['dqs']['score']:.0f}), "
        f"RiskGate {rg.get('action')}."
    ]
    if note:
        parts.append(note)
    if m["top_cells"]:
        top = m["top_cells"][0]
        parts.append(
            f"En güçlü kanaat: {top['symbol']} {top['timeframe']} {top['direction']} "
            f"(skor {top['score']:.0f}, final {top['final']})."
        )
    parts.append(
        f"Paper: equity {ctx['paper']['equity_usd']}, açık pozisyon "
        f"{len(ctx['paper']['open_positions'])}."
    )
    return " ".join(parts), [f"snapshot:{ctx['snapshot_id']}", f"dqs:{ctx['dqs']['status']}"]


_CONTEXT_ONLY_NOTE = (
    " Bu dimensiyon karar zincirinde yalnızca kısıtlayıcı/bağlamdır — "
    "asla pozisyon büyütmez ve RiskGate'i gevşetmez."
)


def _options_answer(ctx: dict) -> tuple[str, list[str]]:
    opts = (ctx.get("deep_data") or {}).get("options") or []
    if not opts:
        return (
            "Options state'te dikkat çeken bir IV/skew rejimi yok (rejim NORMAL "
            "ya da veri doğrulanmadı) — options gate şu an kısıt üretmiyor.",
            ["deep_data:options:none"],
        )
    parts, ev = [], []
    for o in opts[:3]:
        proxy = " (25Δ skew proxy — gerçek greeks değil)" if o.get("is_proxy") else ""
        parts.append(
            f"{o['symbol']}: rejim {o['regime']}, ATM IV {o['atm_iv']}, "
            f"IV-RV {o['iv_rv_spread']}, skew {o['skew_25d']}{proxy}"
        )
        ev.append(f"options:{o['symbol']} {o['regime']}")
    return "Options zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _volatility_answer(ctx: dict) -> tuple[str, list[str]]:
    vol = (ctx.get("deep_data") or {}).get("volatility") or []
    if not vol:
        return (
            "Realized volatilite state'te kısıtlayıcı bir rejim göstermiyor "
            "(NORMAL/LOW veya veri doğrulanmadı) — volatilite gate kısıt üretmiyor.",
            ["deep_data:volatility:none"],
        )
    parts, ev = [], []
    for v in vol[:3]:
        parts.append(
            f"{v['symbol']}/{v['timeframe']}: rejim {v['regime']}, durum "
            f"{v['vol_state']}, z-skor {v['vol_zscore']}"
        )
        ev.append(f"volatility:{v['symbol']}/{v['timeframe']} {v['regime']}")
    return (
        "Volatilite zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE,
        ev,
    )


def _derivatives_answer(ctx: dict) -> tuple[str, list[str]]:
    derivs = (ctx.get("deep_data") or {}).get("derivatives") or []
    if not derivs:
        return (
            "Kripto türev verisi (funding/OI/squeeze) state'te kısıtlayıcı sinyal "
            "göstermiyor ya da doğrulanmadı — türev gate kısıt üretmiyor.",
            ["deep_data:derivatives:none"],
        )
    parts, ev = [], []
    for d in derivs[:3]:
        proxy = " (squeeze proxy — gerçek liquidation değil)" if d.get("is_proxy") else ""
        parts.append(
            f"{d['symbol']}: squeeze {d['squeeze_level']}, funding bias "
            f"{d['funding_bias']}{proxy}"
        )
        ev.append(f"derivatives:{d['symbol']} {d['squeeze_level']}")
    return "Türev zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _rotation_answer(ctx: dict) -> tuple[str, list[str]]:
    rot = (ctx.get("deep_data") or {}).get("rotation") or {}
    if rot.get("status") != "OK":
        return (
            f"Sermaye rotasyonu şu an {rot.get('status', 'UNAVAILABLE')} — "
            "yeterli doğrulanmış veri yok, mock skor üretilmez.",
            [f"rotation:{rot.get('status', 'UNAVAILABLE')}"],
        )
    ev_lines = "; ".join(rot.get("evidence") or []) or "—"
    return (
        f"Sermaye rotasyonu: yön {rot.get('direction')} (skor {rot.get('score')}). "
        f"Kanıt: {ev_lines}.",
        [f"rotation:{rot.get('direction')} {rot.get('score')}"],
    )


def _catalyst_answer(ctx: dict) -> tuple[str, list[str]]:
    cats = (ctx.get("deep_data") or {}).get("catalysts") or []
    if not cats:
        return (
            "Doğrulanmış, yarı-ömrü dolmamış ve kısıtlayıcı bir katalizör (haber "
            "etkisi) state'te yok — catalyst gate kısıt üretmiyor.",
            ["deep_data:catalysts:none"],
        )
    parts, ev = [], []
    for c in cats[:3]:
        assets = ", ".join(c.get("affected_assets") or []) or "genel"
        parts.append(
            f"{c['event_type']} → {c['actionability']} ({assets}; yarı-ömür "
            f"{c.get('half_life_minutes')}dk)"
        )
        ev.append(f"catalyst:{c['event_type']} {c['actionability']}")
    return "Catalyst zekâsı: " + " | ".join(parts) + "." + _CONTEXT_ONLY_NOTE, ev


def _grounded_answer(message: str, ctx: dict) -> tuple[str, list[str]]:
    folded = message.casefold()
    symbol = _detect_symbol(folded)
    timeframe = _detect_timeframe(folded)
    if any(k in folded for k in ("eksik", "missing", "hangi veri")):
        return _missing_data_answer(ctx)
    # v2.7 deep-data niyetleri (RiskGate/why fallback'inden ÖNCE — "volatility
    # neden kısıtladı?" gibi sorular ilgili dimensiyona gitsin).
    if any(k in folded for k in ("options", "opsiyon", "skew", "implied", "term structure")):
        return _options_answer(ctx)
    if any(k in folded for k in ("volatilite", "volatility", "oynaklık", "realized vol", "vol rejim")):
        return _volatility_answer(ctx)
    if any(k in folded for k in ("türev", "turev", "derivative", "funding", "open interest", "squeeze")):
        return _derivatives_answer(ctx)
    if any(k in folded for k in ("rotasyon", "rotation", "sermaye akış", "capital rotation")):
        return _rotation_answer(ctx)
    if any(k in folded for k in ("katalizör", "katalizor", "catalyst", "haber etkisi", "yarı ömür", "half-life", "half life")):
        return _catalyst_answer(ctx)
    if any(k in folded for k in ("riskgate", "risk gate", "risk kapısı", "engelledi", "blocked")):
        return _risk_gate_answer(ctx)
    if symbol and any(
        k in folded for k in ("neden", "niye", "açmadın", "açılmadı", "hold", "why")
    ):
        return _why_no_trade_answer(ctx, symbol, timeframe)
    if any(k in folded for k in ("bekliyor", "ne yapıyor", "waiting", "durum ne")):
        return _waiting_answer(ctx)
    if symbol:
        return _why_no_trade_answer(ctx, symbol, timeframe)
    return _overview_answer(ctx)


def answer(message: str) -> dict:
    """Chat yanıtı — her zaman state-grounded; LLM sadece anlatımı akıcılaştırır."""
    refusal = guard.screen(message)
    if refusal is not None:
        return {
            "answer": refusal,
            "refused": True,
            "evidence_used": ["safety:prompt_injection_guard"],
            "llm": {"mode": llm_client.get_mode(), "model": None, "source": "guard",
                    "cached": False},
        }

    ctx = ctx_mod.build_compact_context()
    grounded, evidence = _grounded_answer(message, ctx)
    mode = llm_client.get_mode()
    base = {
        "refused": False,
        "evidence_used": evidence,
        "snapshot_id": ctx["snapshot_id"],
    }

    client = llm_client.get_client()
    if client is None:
        return {
            **base,
            "answer": grounded,
            "llm": {"mode": mode, "model": None, "source": "fallback", "cached": False,
                    "fallback_reason": "llm_off" if mode == "off" else "no_api_key"},
        }

    digest = ctx_mod.context_digest(ctx)
    msg_hash = hashlib.sha1(message.casefold().strip().encode("utf-8")).hexdigest()[:12]
    cache_key = f"chat|{mode}|{digest}|{msg_hash}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {**base, **cached, "llm": {**(cached.get("llm") or {}), "cached": True}}

    system = guard.SYSTEM_RULES
    user = (
        "STATE BAĞLAMI (tek bilgi kaynağın budur):\n"
        f"{ctx_mod.context_for_prompt(ctx)}\n\n"
        "Deterministik motorun bu soru için çıkardığı kanıt-temelli yanıt:\n"
        f"{grounded}\n\n"
        f"KULLANICI SORUSU: {message}\n\n"
        "Yanıtını YALNIZCA bu bağlama dayandır; bağlamda olmayanı 'state'te yok' "
        "diye belirt. Karar/işlem önerme. Kısa Türkçe yanıt ver."
    )
    max_out = budget.max_tokens_per_request()
    est = (len(system) + len(user)) // 4 + max_out
    comp = client.complete(system, user, max_out) if budget.can_spend(est) else None
    if comp is None:
        reason = "budget_exceeded" if not budget.can_spend(est) else "llm_error"
        return {
            **base,
            "answer": grounded,
            "llm": {"mode": mode, "model": None, "source": "fallback", "cached": False,
                    "fallback_reason": reason},
        }
    budget.record(comp.input_tokens + comp.output_tokens)
    result = {
        "answer": comp.text,
        "llm": {"mode": mode, "model": comp.model, "source": "llm", "cached": False,
                "fallback_reason": None},
    }
    cache.put(cache_key, result)
    return {**base, **result}
