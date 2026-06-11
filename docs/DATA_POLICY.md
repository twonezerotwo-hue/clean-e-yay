# Data Policy — Clean E-yAy

## Tek cümle

**Runtime'da mock veri yok. Gerçek veri veya veri yok.**

## Kurallar

1. `MockProvider` **sadece testlerde** kullanılır.
2. Runtime'da, dashboard'da, paper trading'de, learning'de **mock fallback
   yasak**.
3. `PRICE_USE_MOCK` env değişkeni **default `false`**'tur.
4. Gerçek provider veri getiremezse mock'a düşülmez. Bunun yerine quote
   şu şekilde döner:
   - `value`/`price` = `null`
   - `source` = ilgili provider adı (mock değil)
   - `verified` = `false`
   - `status` = `"DATA_UNAVAILABLE"`
   - `error` = açık sebep (`"provider error"`, `"FRED_API_KEY missing"`,
     `"timeout"`, vs.)
5. FRED özelinde: `FRED_API_KEY` env yoksa quote `value=null`,
   `error="FRED_API_KEY missing"`, `verified=false`, DQS BLOCKED.
6. CoinGecko/YFinance hata verirse: mock fiyat **dönülmez**;
   `value=null`, `error=<provider error>`, `verified=false`, DQS BLOCKED.
7. Test/dev path:
   - `TEST_USE_MOCK=true` → conftest tüm test session'ı için açar; mock
     döner ama her quote `verified=false`, `status="MOCK"` damgalı olur.
   - `PRICE_USE_MOCK=true` runtime'da açıkça verilirse dashboard'da
     kırmızı **"TEST/MOCK MODE"** banner gösterilir.
8. Dashboard veri yok durumlarında:
   - "VERİ YOK"
   - "DATA UNAVAILABLE"
   - "Provider error"
   - "API key missing"
   - "Stale / missing"
   gibi ifadelerle açıkça gösterir.
9. Paper trading:
   - `price is None` veya snapshot DQS BLOCKED → o asset için işlem
     açılmaz.
   - Mock fiyatla paper trade **kesinlikle açılmaz**.
   - DQS BLOCKED → tüm asset'lerde yeni trade durur (RiskGate KILL_SWITCH).
10. Learning:
    - Mock veya `verified=false` snapshot'lar learning dataset'e
      alınmaz.
    - Sadece `verified=true` ve gerçek provider kaynaklı veriler
      learning'e girer.

## DQS status enum

| status     | aralık       | anlam                                   |
|------------|--------------|-----------------------------------------|
| `OK`       | score ≥ 70   | Gerçek veri, kullanılabilir              |
| `DEGRADED` | 40 ≤ s < 70  | Bazı eksiklik var, kararlar zayıflatılır |
| `BLOCKED`  | score < 40   | Veri güvenilmez, yeni trade yok         |
