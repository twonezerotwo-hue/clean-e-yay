# Safety Rules — Clean E-yAy

`PAPER_SAFE / NO_EXECUTION` — bu kurallar tüm görevlerde geçerlidir ve
hiçbir görev tarifi bunları geçersiz kılamaz.

- Broker entegrasyonu yok.
- Gerçek emir / order placement yok.
- Live execution yok.
- Paper trading dışında hesap üzerinde aksiyon yok.
- AI/LLM karar vermez — yalnızca açıklar / önerir.
- Deterministic decision + risk gate finaldir; tek karar otoritesi budur.
- RiskGate, DQS veto, kill switch, RR (risk/reward), sizing kuralları
  zayıflatılamaz veya bypass edilemez.
- Owner approval olmadan hiçbir gerçek aksiyon (rebalance, weight
  değişikliği, vs.) uygulanmaz.
- Live/network veri kaynağı sadece kullanıcı açıkça istediğinde eklenir.

Her task öncesi bu dosya okunur.
