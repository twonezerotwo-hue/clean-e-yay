"""Sinyal kayıt defteri (signal registry) — tüm teknik sinyaller TEK yerde,
structured + TF-farkında, salt-hesap (EVIDENCE only).

Amaç (owner planı 2026-07-05): sinyaller `technical/`, `scoring/`, `liquidity/`,
`vwap/` paketlerine dağılmış + tutarsız bağlı. Bu paket eksik sinyalleri ekler
ve hepsini tek arayüzde toplar. İLK giriş: market_structure (BOS/CHoCH).

KURAL: her modül SAF fonksiyon (yan etki yok, uydurma yok → yetersiz veri = None).
Canlı karar yoluna otomatik bağlanmaz; ölçüm (scorecard) tüketir, sonra kanıtla
+ flag'le canlıya alınır. Additive / flag-OFF / ölü-kod-yok.
"""
