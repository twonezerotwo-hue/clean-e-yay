"""Skor tanılama düzeneği — dev aracı (çalışma zamanında import edilmez).

Üretimdeki skor/giriş-kalitesi fonksiyonlarını gerçek geçmiş barlar üzerinde
bar-bar (look-ahead yok) koşar; ablation, korelasyon, kapı etkisi, giriş-konumu
tabloları, kronolojik train/validation/test ve yürütme (SL/TP/ücret) backtesti
üretir. Kullanım: ``python -m scripts.score_diag.run --help``.
"""
