"""Governor — self-managing katmanın ince orkestrasyonu (observe-only başlar).

Bu paket YENİ bir karar/risk motoru DEĞİLDİR. Var olan modülleri (learning,
decision.shadow, mode, paper) okur ve üstüne iki şey ekler:

- `proposals` — her tipte (weight/mode/threshold/risk/data/strategy) owner
  onayı bekleyen önerilerin tek defteri. Defter yalnızca KAYIT tutar; canlı
  config'i (weights/thresholds/risk/mode) ASLA kendisi değiştirmez. Uygulama
  yalnızca mevcut owner-gated yolların (rebalance approve, mode/store) üzerinden
  yapılır — bu, RiskGate/weights değişikliklerinin denetlenebilir tek kanaldan
  geçmesini korur.
- `report` — "agent bugün ne öğrendi / ne buldu / ne öneriyor / ne owner onayı
  bekliyor" sorularını mevcut store'lardan toplayan read-only özet.

Iron Laws korunur: PAPER_SAFE / NO_EXECUTION, RiskGate final, AI açıklar,
owner approval; her şey additive.
"""
