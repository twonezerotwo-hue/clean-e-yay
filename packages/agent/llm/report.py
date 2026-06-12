"""Persona bölümleri — Market Analyst / Risk Officer / Macro Strategist.

Her persona kompakt state bağlamını okur ve narrative-only bölüm üretir:
summary / concerns / evidence_used / missing_data / actionability /
what_would_change_my_mind.

LLM yoksa (off, anahtar yok, bütçe doldu, network hatası) deterministik
fallback bölümleri üretilir — sistem her koşulda çalışır.
`evidence_used` HER ZAMAN koddan doldurulur (LLM'in kanıt uydurmasına
izin verilmez).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from packages.agent.llm import budget, cache
from packages.agent.llm import client as llm_client
from packages.agent.llm import context as ctx_mod
from packages.agent.llm.guard import SYSTEM_RULES

PERSONAS = ("analyst", "risk_officer", "macro_strategist")

_PERSONA_TITLES = {
    "analyst": "Market Analyst",
    "risk_officer": "Risk Officer",
    "macro_strategist": "Macro Strategist",
}

_PERSONA_BRIEFS = {
    "analyst": (
        "Market Analyst olarak decision matrix'in en güçlü hücrelerini, "
        "candidate vs final farklarını ve timeframe'ler arası tutarlılığı "
        "değerlendir."
    ),
    "risk_officer": (
        "Risk Officer olarak RiskGate, halt, korelasyon cluster'ları ve "
        "blocked_by nedenlerini eleştirel gözle değerlendir; neyin trade'i "
        "engellediğini açıkla."
    ),
    "macro_strategist": (
        "Macro Strategist olarak rejimi, haber/katalizör bağlamını ve "
        "1w/1d üst-timeframe bias'ının alt timeframe'lere etkisini "
        "değerlendir."
    ),
}


@dataclass
class PersonaSection:
    persona: str
    title: str
    summary: str
    concerns: list[str] = field(default_factory=list)
    evidence_used: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    actionability: str = ""
    what_would_change_my_mind: str = ""
    source: str = "fallback"   # "llm" | "fallback"
    model: str | None = None


# ---------- ortak kanıt/eksik-veri çıkarımı (her zaman deterministik) ----------

def _evidence_for(persona: str, ctx: dict) -> list[str]:
    m = ctx["matrix"]
    ev: list[str] = [f"snapshot:{ctx['snapshot_id']}", f"dqs:{ctx['dqs']['status']}"]
    if persona == "analyst":
        ev += [
            f"matrix:{c['symbol']}:{c['timeframe']} {c['candidate']}→{c['final']} ({c['score']:.0f})"
            for c in m["top_cells"][:4]
        ]
    elif persona == "risk_officer":
        rg = m["risk_gate"] or {}
        ev.append(f"risk_gate:{rg.get('action')} — {rg.get('reason')}")
        if ctx["halt"]["active"]:
            ev += [f"halt:{h['type']}@{h['level']}" for h in ctx["halt"]["events"]]
        ev += [f"blocked_by:{b}" for b in m["blocked_by_reasons"][:4]]
        ev += [
            f"cluster:{cl.get('status')} {cl.get('cluster_pct')}"
            for cl in (ctx["correlation_clusters"] or [])[:2]
        ]
    else:  # macro_strategist
        ev.append(f"regime:{m['regime']}")
        ev += [f"news:{t}" for t in ctx["news"][:2]]
        ev += [f"catalyst:{c['title']}" for c in ctx["catalysts"][:2]]
    return ev


def _missing_for(ctx: dict) -> list[str]:
    missing: list[str] = []
    for name, meta in (ctx.get("provider_issues") or {}).items():
        missing.append(f"provider {name}: {meta.get('status', 'sorunlu')}")
    missing += [n for n in ctx["dqs"]["notes"] if n]
    missing += [w for w in ctx.get("warnings") or [] if "DEGRADED" in w]
    return missing[:6]


def _actionability(ctx: dict) -> str:
    if ctx_mod.no_actionable_decision(ctx):
        return (
            "no_actionable_decision — DQS BLOCKED veya risk gate kısıtlayıcı; "
            "hiçbir timeframe'de yeni paper aksiyonu yok."
        )
    actions = ctx["matrix"]["paper_actions"]
    if actions:
        acts = ", ".join(
            f"{a['symbol']} {a['timeframe']} {a['paper_action']}" for a in actions[:4]
        )
        return f"paper aksiyonu mümkün: {acts} (final yetki RiskGate'te)."
    return "izleme modu — hiçbir hücre actionable değil, paper aksiyonu yok."


# ---------- deterministik fallback bölümleri ----------

def _fallback_summary(persona: str, ctx: dict) -> str:
    m = ctx["matrix"]
    if persona == "analyst":
        if not m["top_cells"]:
            return "Decision matrix boş — değerlendirilecek hücre yok."
        top = m["top_cells"][0]
        diffs = len(m["candidate_vs_final_diffs"])
        return (
            f"En güçlü kanaat {top['symbol']} {top['timeframe']} "
            f"{top['direction']} (skor {top['score']:.0f}, final {top['final']}). "
            f"{diffs} hücrede candidate ile final ayrıştı (gate'ler kesti)."
        )
    if persona == "risk_officer":
        rg = m["risk_gate"] or {}
        halt_txt = (
            "Aktif halt VAR: "
            + ", ".join(f"{h['type']}→{h['level']}" for h in ctx["halt"]["events"])
            if ctx["halt"]["active"]
            else "Aktif halt yok"
        )
        return (
            f"RiskGate: {rg.get('action')} — {rg.get('reason')}. {halt_txt}. "
            f"DQS {ctx['dqs']['status']} ({ctx['dqs']['score']:.0f})."
        )
    regime = m["regime"]
    news = "; ".join(ctx["news"][:2]) or "öne çıkan başlık yok"
    return f"Makro rejim {regime}. Gündem: {news}."


def _fallback_concerns(persona: str, ctx: dict) -> list[str]:
    m = ctx["matrix"]
    concerns: list[str] = []
    if persona == "analyst":
        for d in m["candidate_vs_final_diffs"][:3]:
            concerns.append(
                f"{d['symbol']} {d['timeframe']}: {d['candidate']} adayı "
                f"{d['final']}'a düştü ({', '.join(d['blocked_by']) or d['reason']})"
            )
    elif persona == "risk_officer":
        concerns += [f"blocked_by: {b}" for b in m["blocked_by_reasons"][:3]]
        for cl in (ctx["correlation_clusters"] or [])[:2]:
            if cl.get("status") in {"WARNING", "BREACH"}:
                concerns.append(f"korelasyon cluster {cl.get('status')}: {cl.get('symbols')}")
        if ctx["paper"]["daily_pnl_usd"] < 0:
            concerns.append(f"günlük PnL negatif: {ctx['paper']['daily_pnl_usd']}")
    else:
        if m["suspended"]:
            concerns.append("Matrix SUSPENDED — makro görüş aksiyona çevrilemez.")
        for c in ctx["catalysts"][:2]:
            if c.get("importance") == "high":
                concerns.append(f"yüksek önemli katalizör: {c['title']}")
    if not concerns:
        concerns.append("Mevcut state'te öne çıkan ek endişe yok.")
    return concerns


def _fallback_change_mind(persona: str, ctx: dict) -> str:
    if ctx_mod.no_actionable_decision(ctx):
        return "DQS'in OK'e dönmesi ve risk gate kısıtlarının kalkması."
    if persona == "analyst":
        return "Timeframe'ler arası yön uyumunun bozulması veya skorların 50'ye gerilemesi."
    if persona == "risk_officer":
        return "Yeni halt/cluster ihlali oluşması ya da mevcut blokların temizlenmesi."
    return "Rejim etiketinin değişmesi veya yüksek önemli yeni katalizör."


def _fallback_section(persona: str, ctx: dict) -> PersonaSection:
    return PersonaSection(
        persona=persona,
        title=_PERSONA_TITLES[persona],
        summary=_fallback_summary(persona, ctx),
        concerns=_fallback_concerns(persona, ctx),
        evidence_used=_evidence_for(persona, ctx),
        missing_data=_missing_for(ctx),
        actionability=_actionability(ctx),
        what_would_change_my_mind=_fallback_change_mind(persona, ctx),
        source="fallback",
        model=None,
    )


# ---------- LLM yolu ----------

_SECTION_MARKERS = (
    ("SUMMARY:", "summary"),
    ("CONCERNS:", "concerns"),
    ("MISSING_DATA:", "missing_data"),
    ("ACTIONABILITY:", "actionability"),
    ("WHAT_WOULD_CHANGE_MY_MIND:", "what_would_change_my_mind"),
)


def _parse_llm_text(text: str) -> dict | None:
    """Marker bazlı gevşek parse; SUMMARY yoksa None (fallback'e düş)."""
    out: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        matched = False
        for marker, key in _SECTION_MARKERS:
            if stripped.upper().startswith(marker):
                current = key
                out[key] = stripped[len(marker):].strip()
                matched = True
                break
        if not matched and current and stripped:
            out[current] = (out[current] + "\n" + stripped).strip()
    if not out.get("summary"):
        return None
    return out


def _to_list(block: str) -> list[str]:
    items = [ln.strip().lstrip("-•").strip() for ln in (block or "").splitlines()]
    return [i for i in items if i]


def _llm_prompt(persona: str, ctx: dict) -> tuple[str, str]:
    system = SYSTEM_RULES
    user = (
        f"{_PERSONA_BRIEFS[persona]}\n\n"
        "STATE BAĞLAMI (tek bilgi kaynağın budur):\n"
        f"{ctx_mod.context_for_prompt(ctx)}\n\n"
        "Şu formatta yanıt ver (başka hiçbir şey yazma):\n"
        "SUMMARY: <2-3 cümle özet>\n"
        "CONCERNS:\n- <endişe>\n"
        "MISSING_DATA:\n- <eksik veri; yoksa 'yok'>\n"
        "ACTIONABILITY: <tek cümle; karar önerme, sadece mevcut durumu söyle>\n"
        "WHAT_WOULD_CHANGE_MY_MIND: <tek cümle>"
    )
    return system, user


def _estimate_tokens(system: str, user: str, max_out: int) -> int:
    return (len(system) + len(user)) // 4 + max_out


def _llm_section(persona: str, ctx: dict, client) -> tuple[PersonaSection | None, int]:
    """(section, kullanılan_token). Başarısızsa (None, 0) → fallback."""
    system, user = _llm_prompt(persona, ctx)
    max_out = budget.max_tokens_per_request()
    if not budget.can_spend(_estimate_tokens(system, user, max_out)):
        return None, 0
    comp = client.complete(system, user, max_out)
    if comp is None:
        return None, 0
    used = comp.input_tokens + comp.output_tokens
    budget.record(used)
    parsed = _parse_llm_text(comp.text)
    if parsed is None:
        return None, used
    return (
        PersonaSection(
            persona=persona,
            title=_PERSONA_TITLES[persona],
            summary=parsed.get("summary", ""),
            concerns=_to_list(parsed.get("concerns", "")),
            evidence_used=_evidence_for(persona, ctx),
            missing_data=_to_list(parsed.get("missing_data", "")) or _missing_for(ctx),
            actionability=parsed.get("actionability") or _actionability(ctx),
            what_would_change_my_mind=parsed.get("what_would_change_my_mind", ""),
            source="llm",
            model=comp.model,
        ),
        used,
    )


# ---------- giriş noktası ----------

def build_persona_sections(ctx: dict | None = None) -> tuple[list[dict], dict]:
    """(persona bölümleri, llm meta). Bölümler dict (API/cache-serializable).

    no_actionable_decision modunda da bölümler üretilir — ama actionability
    her personada 'no_actionable_decision' der (LLM'e de bağlamla gider).
    """
    ctx = ctx or ctx_mod.build_compact_context()
    digest = ctx_mod.context_digest(ctx)
    mode = llm_client.get_mode()
    cache_key = f"report|{mode}|{digest}"

    cached = cache.get(cache_key)
    if cached is not None:
        meta = dict(cached.get("llm") or {})
        meta["cached"] = True
        return list(cached.get("sections") or []), meta

    client = llm_client.get_client()
    tokens_used = 0
    sections: list[PersonaSection] = []
    any_llm = False
    fallback_reason: str | None = None
    if client is None:
        fallback_reason = "llm_off" if mode == "off" else "no_api_key"

    for persona in PERSONAS:
        section = None
        if client is not None:
            section, used = _llm_section(persona, ctx, client)
            tokens_used += used
            if section is not None:
                any_llm = True
            elif fallback_reason is None:
                fallback_reason = (
                    "budget_exceeded"
                    if not budget.can_spend(budget.max_tokens_per_request())
                    else "llm_error"
                )
        sections.append(section or _fallback_section(persona, ctx))

    meta = {
        "mode": mode,
        "model": getattr(client, "model", None) if any_llm else None,
        "source": "llm" if any_llm else "fallback",
        "fallback_reason": None if any_llm else fallback_reason,
        "cached": False,
        "tokens_used": tokens_used,
        "budget": budget.status(),
    }
    payload = {"sections": [asdict(s) for s in sections], "llm": meta}
    cache.put(cache_key, payload)
    return payload["sections"], meta
