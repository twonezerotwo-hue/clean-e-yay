"""Bölge önerisi grafik çizicisi — SVG (SALT-GÖRSEL; hesap yapmaz, karar vermez).

`zone_proposer`'ın bulduklarını GERÇEK haftalık grafik üstüne çizer ki owner
gözüyle kontrol edip onay/ret verebilsin: mumlar (LOG ölçek — owner log çizer),
destek/direnç trend çizgileri, çizgi kesişimi, log-fib seviyeleri, confluence
bölge bantları, pivotlar; sembolde owner planı varsa (zone_plans.yaml) onun
çekirdek/derin katmanları da AYRI stille bindirilir ("makine vs owner" kıyası).

Renk grameri owner'ın çizim diline aynalanır (2026-07-11 öğretim seansı):
dipleri birleştiren çizgi KIRMIZI, tepe çizgisi YEŞİL, fib retracement SARI,
uzantı MAVİ, kesişim/bölge MOR, owner katmanları TURKUAZ kesikli.

Saf string-SVG (ek bağımlılık yok, deterministik, test edilebilir). API'de
`GET /learning/zone-proposer/chart/{symbol}` (SVG) ve
`GET /learning/zone-proposer/review` (tüm asset'ler tek HTML sayfa) servis eder.
"""
from __future__ import annotations

import html
import math

# Owner renk grameri (koyu TradingView zemini)
_BG = "#131722"
_GRID = "#2a2e39"
_TEXT = "#d1d4dc"
_UP, _DOWN = "#26a69a", "#ef5350"
_SUPPORT = "#ef5350"      # dipleri birleştiren çizgi (owner: kırmızı)
_RESISTANCE = "#4caf50"   # tepe çizgisi (owner: yeşil)
_FIB_RETR = "#ffd54f"     # sarı
_FIB_EXT = "#64b5f6"      # mavi
_ZONE = "#ab47bc"         # mor (owner kesişimi mor daireyle işaretler)
_OWNER = "#26c6da"        # turkuaz — owner planı katmanları
_PIVOT = "#9598a1"

_W, _H = 1160, 640
_ML, _MR, _MT, _MB = 10, 96, 46, 30


def _fmt(p: float) -> str:
    """Fiyat etiketi (owner'ın alıştığı biçimde binlik nokta)."""
    if p >= 1000:
        return f"{p:,.0f}".replace(",", ".")
    if p >= 10:
        return f"{p:.2f}"
    return f"{p:.4f}"


def render_svg(bars: list, analysis: dict, *, title: str,
               owner_plans: list[dict] | None = None) -> str:
    """Analiz + barlardan tek asset'in işaretli SVG grafiği (saf, deterministik).

    `analysis` = zone_proposer.analyze_bars çıktısı (status OK ve `draw` dolu).
    `owner_plans` = zone_plans.yaml'dan bu sembolün planları (opsiyonel)."""
    draw = dict(analysis.get("draw") or {})
    zones = list(analysis.get("zones") or [])
    plans = list(owner_plans or [])
    n = len(bars)
    if n < 2:
        return _empty_svg(title, "veri yok")
    horizon = int(draw.get("horizon", 26))
    total = n + horizon  # x-domain: barlar + gelecek projeksiyonu

    # --- Y domain (log): barlar + bölgeler + fibler + owner katmanları ---
    prices: list[float] = []
    for b in bars:
        prices.extend((b.low, b.high))
    for z in zones:
        prices.extend((z["low"], z["high"]))
    for fib_key in ("fib_retr", "fib_ext"):
        fib = draw.get(fib_key)
        if fib:
            prices.extend(float(v) for v in fib["levels"].values())
    for pl in plans:
        prices.extend((pl["deep"], pl["core_low"], pl["core_high"]))
    prices = [p for p in prices if p > 0]
    lo_log = math.log10(min(prices)) - 0.02
    hi_log = math.log10(max(prices)) + 0.02

    plot_w, plot_h = _W - _ML - _MR, _H - _MT - _MB

    def x(i: float) -> float:
        return _ML + (i / max(total - 1, 1)) * plot_w

    def y(p: float) -> float:
        return _MT + (hi_log - math.log10(max(p, 1e-12))) / (hi_log - lo_log) * plot_h

    s: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" '
        f'viewBox="0 0 {_W} {_H}" font-family="Arial,sans-serif">',
        f'<rect width="{_W}" height="{_H}" fill="{_BG}"/>',
        f'<clipPath id="plot"><rect x="{_ML}" y="{_MT}" width="{plot_w}" '
        f'height="{plot_h}"/></clipPath>',
    ]

    # --- Fiyat ızgarası (log-aralıklı ~6 tick) ---
    for k in range(7):
        gl = lo_log + (hi_log - lo_log) * k / 6
        gy = y(10 ** gl)
        s.append(f'<line x1="{_ML}" y1="{gy:.1f}" x2="{_ML + plot_w}" y2="{gy:.1f}" '
                 f'stroke="{_GRID}" stroke-width="1"/>')
        s.append(f'<text x="{_ML + plot_w + 6}" y="{gy + 4:.1f}" fill="{_TEXT}" '
                 f'font-size="12">{_fmt(10 ** gl)}</text>')

    # --- Zaman ekseni (yıl etiketleri: yılın ilk barı) ---
    seen_years: set[int] = set()
    for i, b in enumerate(bars):
        yr = b.ts.year
        if yr not in seen_years:
            seen_years.add(yr)
            s.append(f'<text x="{x(i):.1f}" y="{_H - 8}" fill="{_TEXT}" '
                     f'font-size="12">{yr}</text>')

    s.append('<g clip-path="url(#plot)">')

    # --- Confluence bölge bantları (mor; güçlü olan daha koyu) ---
    for rank, z in enumerate(zones):
        op = max(0.10, 0.30 - rank * 0.05)
        zy1, zy2 = y(z["high"]), y(z["low"])
        s.append(f'<rect x="{_ML}" y="{zy1:.1f}" width="{plot_w}" '
                 f'height="{max(zy2 - zy1, 2):.1f}" fill="{_ZONE}" opacity="{op:.2f}"/>')

    # --- Mumlar ---
    cw = max(1.0, plot_w / total * 0.7)
    for i, b in enumerate(bars):
        cx = x(i)
        col = _UP if b.close >= b.open else _DOWN
        s.append(f'<line x1="{cx:.1f}" y1="{y(b.high):.1f}" x2="{cx:.1f}" '
                 f'y2="{y(b.low):.1f}" stroke="{col}" stroke-width="1"/>')
        top, bot = sorted((y(b.open), y(b.close)))
        s.append(f'<rect x="{cx - cw / 2:.1f}" y="{top:.1f}" width="{cw:.1f}" '
                 f'height="{max(bot - top, 1):.1f}" fill="{col}"/>')

    # --- Pivotlar (küçük noktalar) ---
    for p in draw.get("pivots") or []:
        s.append(f'<circle cx="{x(p["i"]):.1f}" cy="{y(p["price"]):.1f}" r="2.2" '
                 f'fill="{_PIVOT}" opacity="0.9"/>')

    # --- Trend çizgileri (geleceğe projekte; owner renkleri) ---
    for ln in draw.get("lines") or []:
        col = _SUPPORT if ln["kind"] == "support_line" else _RESISTANCE
        x1, x2 = 0, total - 1
        p1 = 10 ** (ln["slope"] * x1 + ln["intercept"])
        p2 = 10 ** (ln["slope"] * x2 + ln["intercept"])
        s.append(f'<line x1="{x(x1):.1f}" y1="{y(p1):.1f}" x2="{x(x2):.1f}" '
                 f'y2="{y(p2):.1f}" stroke="{col}" stroke-width="2"/>')

    # --- Çizgi kesişimi (mor daire — owner işareti) ---
    cross = draw.get("cross")
    if cross:
        s.append(f'<circle cx="{x(cross["i"]):.1f}" cy="{y(cross["price"]):.1f}" '
                 f'r="9" fill="none" stroke="{_ZONE}" stroke-width="2.5"/>')

    # --- Fib seviyeleri (kesikli yatay; sarı retr, mavi ext) ---
    for fib_key, col in (("fib_retr", _FIB_RETR), ("fib_ext", _FIB_EXT)):
        fib = draw.get(fib_key)
        if not fib:
            continue
        for lv, price in fib["levels"].items():
            fy = y(float(price))
            s.append(f'<line x1="{_ML}" y1="{fy:.1f}" x2="{_ML + plot_w}" '
                     f'y2="{fy:.1f}" stroke="{col}" stroke-width="1" '
                     f'stroke-dasharray="6 4" opacity="0.85"/>')
            s.append(f'<text x="{_ML + 6}" y="{fy - 3:.1f}" fill="{col}" '
                     f'font-size="11">{lv} ({_fmt(float(price))})</text>')

    # --- Owner planı katmanları (turkuaz kesikli — "makine vs owner") ---
    for pl in plans:
        for price, tag in ((pl["core_high"], "OWNER çekirdek üst"),
                           (pl["core_low"], "OWNER çekirdek alt"),
                           (pl["deep"], "OWNER derin")):
            py = y(price)
            s.append(f'<line x1="{_ML}" y1="{py:.1f}" x2="{_ML + plot_w}" '
                     f'y2="{py:.1f}" stroke="{_OWNER}" stroke-width="1.5" '
                     f'stroke-dasharray="2 5"/>')
            s.append(f'<text x="{_ML + plot_w - 200}" y="{py - 3:.1f}" '
                     f'fill="{_OWNER}" font-size="11">{tag} {_fmt(price)}</text>')

    s.append("</g>")

    # --- Bölge etiketleri (sol kenar, bant ortasına) ---
    for z in zones:
        zy = y(z["mid"])
        label = f'★{z["confluence"]} araç: {_fmt(z["low"])}–{_fmt(z["high"])}'
        s.append(f'<text x="{_ML + 6}" y="{zy + 4:.1f}" fill="{_ZONE}" '
                 f'font-size="12" font-weight="bold">{html.escape(label)}</text>')

    # --- Başlık + lejant ---
    s.append(f'<text x="{_ML + 4}" y="20" fill="{_TEXT}" font-size="16" '
             f'font-weight="bold">{html.escape(title)}</text>')
    legend = [(_SUPPORT, "dip çizgisi"), (_RESISTANCE, "tepe çizgisi"),
              (_FIB_RETR, "fib"), (_FIB_EXT, "uzantı"), (_ZONE, "bölge")]
    if plans:
        legend.append((_OWNER, "owner planı"))
    lx = _ML + 4
    for col, lab in legend:
        s.append(f'<rect x="{lx}" y="28" width="10" height="10" fill="{col}"/>')
        s.append(f'<text x="{lx + 14}" y="37" fill="{_TEXT}" font-size="11">{lab}</text>')
        lx += 14 + 8 * len(lab) + 18
    s.append("</svg>")
    return "".join(s)


def _empty_svg(title: str, reason: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="120" '
        f'viewBox="0 0 {_W} 120" font-family="Arial,sans-serif">'
        f'<rect width="{_W}" height="120" fill="{_BG}"/>'
        f'<text x="12" y="40" fill="{_TEXT}" font-size="15">'
        f'{html.escape(title)} — {html.escape(reason)}</text></svg>'
    )


# ---------------------------------------------------------------------------
# Veri bağlama (asla raise etmez) + inceleme sayfası
# ---------------------------------------------------------------------------

def chart_svg(symbol: str) -> str | None:
    """Sembolün taze analizle işaretli grafiği. Veri yoksa None."""
    from packages.learning import zone_plan_shadow, zone_proposer

    try:
        bars = zone_proposer._weekly_bars(symbol)
        if not bars:
            return None
        analysis = zone_proposer.analyze_bars(bars, zone_proposer._cfg())
        plans = [p for p in zone_plan_shadow.load_plans() if p["symbol"] == symbol]
        title = f"{symbol} — haftalık (LOG) · fiyat {_fmt(bars[-1].close)}"
        if analysis.get("status") != "OK":
            return _empty_svg(title, str(analysis.get("status")))
        return render_svg(bars, analysis, title=title, owner_plans=plans)
    except Exception:
        return None


_HONESTY = (
    "Makine ADAY önerir, bölge SEÇMEZ. Owner kararı: bölgeler sen İPTAL EDENE "
    "KADAR onaylı sayılır. İptal edilen bölge canlı SL/TP yerleşimine girmez; "
    "onaylılar zone_influence flag'i AÇIKKEN hesaba katılır (default KAPALI — "
    "5y kanıt + owner onayı olmadan canlıya etki yok). Her karar kalibrasyon "
    "verisi olarak birikir."
)

# Buton JS'i — same-origin POST; başarıda sayfayı tazeler. Saf/inline, bağımlılık yok.
_VERDICT_JS = (
    "<script>async function zv(sym,low,high,action){"
    "const r=await fetch('/api/v1/learning/zone-proposer/verdict',{method:'POST',"
    "headers:{'content-type':'application/json'},"
    "body:JSON.stringify({symbol:sym,low:low,high:high,action:action})});"
    "if(r.ok){location.reload();}else{alert('Kaydedilemedi: '+r.status);}}"
    "</script>"
)


def review_html() -> str:
    """Tüm evrenin işaretli grafikleri tek sayfada (confluence sırasıyla).

    Owner'ın onay/ret turu için: her asset'in gerçek grafiği + bölge tablosu.
    Artifact yoksa yönlendirme notu döner (worker koşunca oluşur)."""
    from packages.learning import zone_proposer

    art = zone_proposer._load()
    head = (
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        "<title>Aday bölge incelemesi</title>"
        f"<style>body{{background:{_BG};color:{_TEXT};font-family:Arial,"
        "sans-serif;margin:16px}}h1{font-size:20px}h2{font-size:16px;"
        "margin:24px 0 6px}table{border-collapse:collapse;font-size:13px;"
        "margin:6px 0 14px}td,th{border:1px solid #2a2e39;padding:4px 10px}"
        f".honesty{{color:{_FIB_RETR};font-size:13px;max-width:960px}}"
        "button{cursor:pointer;border:1px solid #555;border-radius:3px;"
        "padding:2px 8px;font-size:12px;background:#2a2e39;color:#d1d4dc}"
        f"button.iptal{{border-color:{_DOWN};color:{_DOWN}}}"
        f"button.onay{{border-color:{_UP};color:{_UP}}}"
        f".b-onayli{{color:{_UP};font-weight:bold}}"
        f".b-iptal{{color:{_DOWN};font-weight:bold}}</style>"
        f"{_VERDICT_JS}"
        "</head><body><h1>Aday bölge incelemesi — makine önerir, owner süzer</h1>"
        f"<p class='honesty'>{html.escape(_HONESTY)}</p>"
    )
    if not art:
        return head + "<p>Henüz artifact yok — learning worker koşunca oluşur.</p></body></html>"

    from packages.learning import zone_approval

    parts = [head, f"<p>Üretim: {html.escape(str(art.get('generated_at')))}</p>"]
    assets = [a for a in (art.get("assets") or []) if a.get("zones")]
    assets.sort(key=lambda a: -a["zones"][0]["confluence"])
    for a in assets:
        sym = str(a["symbol"])
        svg = chart_svg(sym)
        if svg is None:
            continue
        parts.append(f"<h2>{html.escape(sym)}</h2>")
        parts.append(svg)
        rows = []
        for z in a["zones"]:
            verdict = zone_approval.verdict_for(sym, z["low"], z["high"])
            badge = ("<span class='b-onayli'>ONAYLI</span>" if verdict == "onayli"
                     else "<span class='b-iptal'>İPTAL</span>")
            if verdict == "onayli":
                btn = (f"<button class='iptal' onclick=\"zv('{sym}',{z['low']},"
                       f"{z['high']},'iptal')\">İptal et</button>")
            else:
                btn = (f"<button class='onay' onclick=\"zv('{sym}',{z['low']},"
                       f"{z['high']},'onay')\">Tekrar onayla</button>")
            rows.append(
                f"<tr><td>{z['confluence']}</td><td>{_fmt(z['low'])}–{_fmt(z['high'])}</td>"
                f"<td>{html.escape(', '.join(z['sources']))}</td>"
                f"<td>%{z['dist_pct']} {html.escape(z['side'])}</td>"
                f"<td>{html.escape(str(z.get('at') or '—'))}</td>"
                f"<td>{badge}</td><td>{btn}</td></tr>"
            )
        parts.append(
            "<table><tr><th>araç</th><th>bölge</th><th>kaynaklar</th>"
            f"<th>uzaklık</th><th>tarih</th><th>durum</th><th></th></tr>"
            f"{''.join(rows)}</table>"
        )
    parts.append("</body></html>")
    return "".join(parts)


__all__ = ["chart_svg", "render_svg", "review_html"]
