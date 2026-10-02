# Clean E-yAy v2.3 — Full Trading Intelligence Architecture (Final, Consolidated)

> Bu belge v2.1 (Full Architecture) ve v2.2 (Policy & Conflict Resolution
> Addendum) dokümanlarını birleştirir, tespit edilen tüm mantıksal
> boşlukları kapatır ve tek başına yeterli, bağımsız bir spec olarak
> yazılmıştır. Artık v2.1/v2.2'ye referans gerekmez — implementasyon bu
> belgeden yapılır.

---

## 0. Ana Tanım

Clean E-yAy v2.3, tek skorla long/short veren klasik bir trading bot
değildir.

Clean E-yAy v2.3 şudur:

```text
Multi-timeframe piyasa okuma sistemi
+ Elliott scenario engine (opsiyonel kanıt katmanı, zorunlu değil)
+ Fibonacci / RSI divergence / volume / liquidity validation
+ market structure analysis
+ setup classification
+ multi-timeframe alignment matrix (her kombinasyon için fallback formülü)
+ agent mode control
+ policy / threshold config (tüm nitel terimler sayısal eşiğe bağlı)
+ conflict resolver (sabit otorite sırası + ayrı log sırası)
+ trade profile selection
+ SL / TP / position size planning (sabit öncelikli, tek formülle)
+ historical edge / winrate analysis (fuzzy similarity, sabit N tanımı)
+ risk gate
+ paper trading
+ position management
+ post-trade learning
+ missed opportunity analysis (TTL'li)

```

Sistemin ana amacı:

```text
Fiyat yükselecek mi düşecek mi?

```

sorusuna tek cevap vermek değildir. Asıl amaç:

```text
Piyasa hangi fazda?
Hangi setup var?
Bu setup hangi timeframe'e ait?
Bu setup scalp mi, intraday mi, swing mi?
Bu mod şu an aktif mi?
Timeframe'ler birbiriyle uyumlu mu, çakışıyor mu?
Giriş için doğru yer mi?
Stop-loss ve take-profit mantıklı mı?
Geçmişte benzer setup kaç kez çalışmış?
Hangi kural hangi kuralı geçersiz kılıyor?
RiskGate işleme izin veriyor mu?
İşlem açılmalı mı, beklenmeli mi, engellenmeli mi?

```

sorularına **deterministik, açıklanabilir, izlenebilir (replay edilebilir)
ve paper-safe** şekilde cevap vermektir.

---

## 1. Temel Prensipler

### 1.1 Paper-only güvenlik

İlk çalışma modu kesinlikle:

```text
PAPER_ONLY
NO_REAL_BROKER
NO_REAL_EXECUTION
NO_AUTO_LIVE_ORDER

```

olmalıdır. Sistem gerçek broker'a otomatik emir göndermez. Pozisyon
kapatma dahil her aksiyon paper lifecycle üzerinden yürütülür (bkz. §27,
§35.4).

### 1.2 LLM karar vermez

LLM sadece anlatır, özetler, raporlar. Final karar backend tarafından
deterministic olarak verilir.

```text
LLM = narrator / explainer
Backend = decision maker
Conflict Resolver = çelişkileri sabit kurallarla çözen ara katman
RiskGate = final safety gate

```

### 1.3 Deterministiklik zorunluluğu (yeni — v2.3)

Hiçbir nitel terim backend içinde serbest yorumla kullanılmaz:

```text
"mid-range", "geç giriş", "düşük örnek", "zayıf historical edge",
"counter-context", "reduced size", "degraded data"

```

Bu kavramların hepsi `config/policy_v2.3.yaml` içindeki bir eşiğe, enum'a
veya karar matrisine bağlıdır (bkz. §6). Bir kuralın config karşılığı
yoksa o kural koda giremez.

### 1.4 Tek skorla işlem açılmaz

Eski mantık:

```text
score yüksek → long
score düşük → short

```

Yeni mantık:

```text
consensus score        = directional pressure
setup classifier        = işlem fikri
alignment matrix          = timeframe'ler birbiriyle uyumlu mu
trigger engine            = şimdi girilir mi?
agent mode control        = bu işlem modu aktif mi?
historical edge            = geçmişte bu setup çalışmış mı?
SL/TP planner              = seviyeler (sabit öncelik sırasıyla)
position sizing formula    = tek formülle size (çarpımsal çöküş yok)
conflict resolver           = hangi kural hangi kuralı geçersiz kılıyor
RiskGate                     = son güvenlik izni

```

### 1.5 Elliott kesin sayım değildir ve zorunlu değildir

Otomatik Elliott motoru hiçbir zaman tek doğru sayım iddia etmez ve
hiçbir setup'ın ön koşulu değildir (detay §9.6). Her zaman:

```text
primary scenario
alternative scenarios
confidence
invalidation
target zone

```

üretir, ama NO_VALID_COUNT dönerse sistem ölmez — diğer katmanlarla
devam eder.

### 1.6 Setup olmadan işlem yok

İşlem açma zinciri:

```text
Valid Data
+ Valid Market Mode
+ Valid Setup
+ Valid Multi-Timeframe Alignment (fallback formülü dahil her durumda sonuçlanır)
+ Active Agent Mode
+ Acceptable Location
+ Trigger Confirmed
+ Valid SL / TP / RR
+ Historical Edge Acceptable
+ Conflict Resolver Pass (otorite sırasına göre)
+ RiskGate Pass
= Paper Trade Allowed

```

---

## 2. Ana Sistem Akışı

Full pipeline (v2.3 — Policy Config ve Conflict Resolver eklendi):

```text
Data Ingestion
→ Data Quality / DQS
→ Market Snapshot
→ Multi-Timeframe Analysis
→ Market Mode Detection
→ Market Structure Analysis
→ Pivot / Swing Detection
→ Elliott Scenario Engine
→ Fibonacci Validation
→ Zone Engine
→ Liquidity Sweep Engine
→ Momentum / Divergence Engine
→ Volume Validation Engine
→ VWAP / Anchored VWAP Engine
→ Exhaustion Score
→ Location Score
→ Setup Classifier
→ Multi-Timeframe Alignment Matrix
→ Clean E-yAy Consensus Alignment
→ Trigger Engine
→ Trade Profile Selector
→ Agent Mode Control
→ SL / TP Planner
→ Historical Edge Engine
→ Position Sizing Engine (tek formül)
→ Conflict Resolver
→ RiskGate
→ Final Decision Engine
→ Paper Trading Engine
→ Position Management
→ Trade Journal
→ Post-Trade Learning
→ Missed Opportunity Engine
→ Mistake Memory
→ Dashboard / Explainability

```

Policy / Threshold Config (§6) pipeline'ın **her** adımına yatay olarak
bağlıdır — her katman kendi eşiklerini buradan okur, hardcode etmez.

---

## 3. Data Layer

### 3.1 Görev

```text
OHLCV verisi toplar
multi-asset veri toplar
multi-timeframe veri toplar
timestamp kontrolü yapar
eksik mum kontrolü yapar
spread / slippage kontrolü yapar
volume kalitesi kontrolü yapar
price sanity kontrolü yapar
DQS üretir

```

### 3.2 Timeframe desteği

Zorunlu: `1D, 4H, 1H, 15M`. Gelişmiş scalp için: `5M, 1M`. Daha büyük
bağlam için: `1W`.

### 3.3 DQS kararları (eşikler sayısal — §6)

```text
DQS_OK       (dqs.ok_min = 0.80 ve üzeri)       → analiz yapılabilir
DQS_DEGRADED (dqs.degraded_min..ok_min = 0.60–0.79) → §15'teki matrise göre watch/reduced size
DQS_BAD      (dqs.bad_below = altı, < 0.60)     → no trade, BLOCKED

```

Kural: `DQS_BAD` ise hiçbir setup işlem açamaz; bu Conflict Resolver'da
Hard Safety (§14) tarafından override edilemez şekilde uygulanır.

---

## 4. Multi-Timeframe Context Layer

Her timeframe'in görevi farklıdır:

```text
1W / 1D → büyük resim, ana trend, ana Elliott bağlamı
4H      → setup alanı
1H      → confirmation alanı
15M     → entry / scalp / yakın SL-TP
5M / 1M → mikro scalp entry

```

### 4.1 Temel kural

Üst timeframe bağlam verir. Alt timeframe giriş verir.

```text
1D tek başına trade açtırmaz.
15M tek başına büyük swing trade açtırmaz.

```

### 4.2 Örnek

```text
1D:  Wave 4 correction likely
4H:  C wave ending near fib support
1H:  bullish divergence + structure break
15M: retest held, trigger confirmed

Sonuç: TACTICAL_LONG veya SCALP_LONG (Agent Mode + Alignment Matrix sonrasına göre)

```

Bu görev ayrımının çakışma çözümü için **Multi-Timeframe Alignment
Matrix**'e (§13) bağlandığını unutmayın — sadece "üst bağlam, alt giriş"
kuralı çakışma durumlarını çözmeye yetmez.

---

## 5. Agent Mode Control Layer

### 5.1 Amaç

Agent Mode Control, sistemin hangi işlem modlarına odaklanacağını
belirler. Sistem her setup'ı bulabilir ama her setup'ı işleme çevirmek
zorunda değildir.

```text
SCALP / INTRADAY / TACTICAL / SWING / POSITION

```

Ek olarak:

```text
allow_counter_context_trades
allow_reversal_trades
allow_trend_follow_trades
allow_range_trades
allow_breakout_trades

```

### 5.2 Örnek config

```json
{
  "enabled_trade_profiles": ["INTRADAY", "TACTICAL", "SWING"],
  "disabled_trade_profiles": ["SCALP"],
  "focus_mode": "TACTICAL",
  "allow_counter_context_trades": false,
  "allow_reversal_trades": true,
  "allow_trend_follow_trades": true,
  "allow_range_trades": true,
  "allow_breakout_trades": true
}
```

### 5.3 Scalp kapalıysa

```text
Setup detected: SCALP_LONG
Mode state: SCALP_DISABLED
Final action: WATCH (watch_disabled_profiles=true ise) veya NO_TRADE
Reason: scalp mode disabled

```

### 5.4 Sadece swing modu

```json
{ "enabled_trade_profiles": ["SWING", "POSITION"], "focus_mode": "SWING" }
```

1D/4H setup'lar öncelikli olur; 15M scalp setup'ları işlem açtırmaz, sadece
entry timing için kullanılabilir.

### 5.5 Scalp + intraday modu

```json
{ "enabled_trade_profiles": ["SCALP", "INTRADAY"], "disabled_trade_profiles": ["SWING", "POSITION"] }
```

Kısa vadeli fırsatlar taranır; TP/SL yakın tutulur; time-stop zorunlu;
büyük timeframe sadece bağlam.

### 5.6 Counter-context kapalıysa

```text
1D bullish, 15M short scalp setup var
→ normalde COUNTER_CONTEXT_SCALP_SHORT
→ counter-context kapalıysa: NO_TRADE, Reason: counter-context trades disabled

```

### 5.7 Bu katman RiskGate değildir

```text
Agent Mode Control: Bu tarz işlem şu an açık mı? (yeni giriş filtresi)
RiskGate:            Bu işlem güvenli mi? (güvenlik filtresi)

```

Agent Mode Control **yalnızca yeni girişi** filtreler. Açık pozisyon
yönetimi her zaman RiskGate + Position Management'a aittir (§5.8, §27.3,
§35.4) — pozisyon kapatma kararı bir risk kararıdır, sadece bir mode-config
flag'i ile tetiklenmez.

### 5.8 Açık Pozisyon ile Agent Mode İlişkisi (netleştirildi)

```text
Scalp mode kapatıldıysa:
  1. Yeni scalp girişleri hemen kapanır.
  2. Mevcut scalp pozisyonları RiskGate + Position Management kurallarıyla yönetilir.
  3. close_disabled_profile_positions_default=true ise, kapatma RiskGate
     onayından geçmeden tetiklenmez (close_requires_riskgate_pass: true, §6).

```

---

## 6. Policy / Threshold Config

Dosya: `config/policy_v2.3.yaml`. Tüm sayısal eşikler buradan okunur, kod
içinde hardcode edilmez.

```yaml
version: "2.3"

dqs:
  ok_min: 0.80
  degraded_min: 0.60
  bad_below: 0.60

market_location:
  good_location_min: 70
  mid_range_min: 40
  bad_location_below: 40
  max_mid_range_position_in_range_pct: 0.35

exhaustion:
  downside_extreme_max: 20
  neutral_min: 40
  neutral_max: 60
  upside_extreme_min: 80

setup_confidence:
  confirmed_min: 75
  watch_min: 55
  weak_below: 55

trigger:
  confirmed_min: 70
  missing_below: 70

elliott:
  evidence_weight_high_min: 75
  evidence_weight_low_max: 60
  reversal_requires_evidence: true

historical_edge:
  similarity_similar_min: 0.70
  similarity_strong_min: 0.85
  min_sample_observe_only: 20
  min_sample_usable: 50
  min_sample_strong: 100
  min_winrate_trade_allowed: 0.52
  min_average_r_trade_allowed: 0.10
  strong_negative_winrate_max: 0.45
  strong_negative_avg_r_max: -0.10

risk_reward:
  scalp_min_rr: 1.20
  intraday_min_rr: 1.50
  tactical_min_rr: 1.80
  swing_min_rr: 2.00
  position_min_rr: 2.50
  max_stop_distance_atr_mult: 2.50

position_sizing:
  base_risk_pct: 0.50
  max_risk_pct: 1.00
  min_risk_pct: 0.05
  floor_risk_pct: 0.00
  blend_mode: "weighted_additive_clamped"
  profile_multiplier:
    SCALP: 0.25
    INTRADAY: 0.50
    TACTICAL: 0.75
    SWING: 1.00
    POSITION: 1.00
  counter_context_multiplier: 0.35
  degraded_dqs_multiplier: 0.35
  high_volatility_multiplier: 0.50
  mistake_memory_reduce_multiplier: 0.50
  soft_factor_weights:
    alignment: 0.30
    confidence: 0.25
    historical_edge: 0.20
    mistake_memory: 0.15
    profile: 0.10

agent_mode:
  disabled_profile_action: "NO_TRADE"
  disabled_profile_watch_tracking: true
  close_disabled_profile_positions_default: false
  close_requires_riskgate_pass: true

missed_opportunity:
  watch_ttl_bars:
    SCALP: 12
    INTRADAY: 24
    TACTICAL: 48
    SWING: 80
    POSITION: 120
  max_tracking_days: 30
  min_missed_r: 1.0

alignment:
  fallback_rule: "majority_with_recency_weight"
  recency_weights: [0.40, 0.30, 0.20, 0.10]   # [1D/1W, 4H, 1H, 15M]
  fully_aligned_min: 0.70
  partially_aligned_min: 0.30

historical_similarity_weights:
  setup_type: 0.20
  trade_profile: 0.15
  market_mode: 0.12
  timeframe_stack: 0.12
  asset_class: 0.08
  elliott_scenario: 0.08
  fib_score_bucket: 0.07
  divergence_state: 0.06
  volume_state: 0.05
  volatility_regime: 0.04
  trigger_type: 0.03

sizing_multipliers:
  alignment: {FULLY_ALIGNED: 1.00, PARTIALLY_ALIGNED: 0.70, COUNTER_CONTEXT: 0.35, CONFLICTING: 0.00, NO_ALIGNMENT: 0.00}
  confidence: {high: 1.00, medium: 0.70, low: 0.40, weak: 0.00}
  historical_edge: {strong_positive: 1.00, weak_positive: 0.80, neutral: 0.60, weak_negative: 0.35, strong_negative: 0.00}
  dqs: {OK: 1.00, DEGRADED: 0.35, BAD: 0.00}
  volatility: {NORMAL: 1.00, HIGH: 0.50, EXTREME: 0.00}
  riskgate: {PASS: 1.00, CAUTION: 0.50, NO_POSITION_INCREASE: 0.00, KILL_SWITCH: 0.00}
  mistake_memory: {CLEAN: 1.00, CAUTION: 0.70, AVOID_SIMILAR: 0.00}
```

Kural: Bu dosyada karşılığı olmayan hiçbir nitel terim kod içinde
kullanılamaz; her PR'da yeni bir eşik gerekiyorsa önce buraya eklenir.

---

## 7. Market Mode Engine

### 7.1 Market mode tipleri

```text
TRENDING / RANGING / BREAKOUT / FAILED_BREAKOUT / CHOPPY / HIGH_VOLATILITY / LOW_VOLATILITY

```

### 7.2 Okuyacağı veriler

```text
HH/HL/LH/LL, EMA slope, ADX/trend strength, ATR expansion,
range high/low, breakout kalitesi, fake breakout, volume confirmation

```

### 7.3 Kullanım

```text
Range piyasada trend-follow azaltılır.
Trend piyasada erken reversal azaltılır.
Choppy piyasada işlem azaltılır (alignment §13.3'te NO_ALIGNMENT override).
High volatility durumunda size düşürülür (sizing_multipliers.volatility).

```

---

## 8. Market Structure Engine

### 8.1 Okuyacağı yapılar

```text
HH, HL, LH, LL, Break of Structure, Change of Character,
Retest, Failed Retest, Range High, Range Low

```

### 8.2 Reversal kuralı

```text
Reversal trade için structure dönüşü gerekir.
Elliott C wave bitiyor olabilir + Fib support var + RSI divergence var
ama 1H structure yukarı kırılmadıysa: Action = WATCH

```

---

## 9. Pivot / Swing Detection Engine

### 9.1 Görev

```text
major/minor swing high/low bul, pivot degree belirle,
ATR distance filtresi uygula, minimum bar separation uygula

```

### 9.2 Çıktı

```text
P0, P1, P2, P3, P4, P5

```

Bu pivotlar Elliott scenario engine'e girer.

---

## 10. Elliott Scenario Engine

### 10.1 Temel prensip

Sistem kullanıcıdan sayım almaz, otomatik sayım yapar, ama tek kesin
sonuç vermez.

### 10.2 Çıktı

```text
primary_scenario, alternative_scenarios, confidence, wave_points,
invalidation_price, target_zone, bias, degree, timeframe

```

### 10.3 Senaryo tipleri

```text
IMPULSE_1_2_3_4_5, IMPULSE_5_ENDING, WAVE_3_EXTENSION, WAVE_4_CORRECTION,
ABC_CORRECTION, C_WAVE_ENDING, COMPLEX_CORRECTION, NO_VALID_COUNT

```

### 10.4 Elliott hard rules

```text
Wave 2, Wave 1 başlangıcını geçmemeli.
Wave 3 en kısa dalga olmamalı.
Wave 4, Wave 1 alanına girmemeli.
Wave 3 genelde güçlü momentum/hacim taşımalı.
Wave 5 sonunda divergence aranabilir.
ABC yapısı oranlı olmalı; C wave A ile uyumlu extension üretmeli;
B wave makul retracement alanında kalmalı.

```

### 10.5 Örnek çıktı

```text
BTCUSD 4H
Primary scenario: C_WAVE_ENDING
Bias: REVERSAL_LONG
Confidence: 72%
Invalidation: C wave low below
Alternative: Correction still ongoing

```

### 10.6 Opsiyonellik Kuralı (kritik düzeltme — v2.1 §9.6'nın netleşmiş hali)

Elliott motoru tek başına işlem açmaz ve **hiçbir setup'ın ön koşulu
değildir**:

```text
Elliott scenario = evidence (kanıt katmanı)
Trade decision = full pipeline sonucu

```

Elliott `NO_VALID_COUNT` dönerse:

```text
Elliott NO_VALID_COUNT
  + trend structure strong   → TREND setup ALLOWED
  + range structure clear    → RANGE setup ALLOWED
  + breakout confirmed        → BREAKOUT setup ALLOWED
  + scalp trigger present     → SCALP setup ALLOWED
  + reversal evidence only    → reversal setup NOT ALLOWED
                                 (elliott.reversal_requires_evidence: true)

```

Elliott confidence ağırlık kuralı (`elliott.*`, §6):

```text
confidence >= evidence_weight_high_min (75) → güçlü kanıt, Setup
  Classifier reversal/continuation olasılığını yüksek ağırlıkla kullanır
confidence < evidence_weight_low_max (60)    → zayıf kanıt, düşük ağırlık
  (informational only, setup kararını değiştirmez)
60 <= confidence < 75                          → orta ağırlık
NO_VALID_COUNT                                   → Elliott evidence = 0,
  sistem tamamen diğer teknik katmanlarla (structure, volume, vwap,
  divergence) karar verir

```

Yani Elliott yoksa sistem ölmez; sadece Elliott destekli setup'ların
puanı düşer, reversal setup'lar engellenir.

---

## 11. Fibonacci Validation Engine

### 11.1 Impulse fib kuralları

```text
Wave 2 retracement: 0.5 / 0.618 / 0.786
Wave 3 extension:   1.618 / 2.618
Wave 4 retracement: 0.236 / 0.382 / 0.5
Wave 5 projection:  0.618 / 1.0 / 1.618

```

### 11.2 Correction fib kuralları

```text
B wave retracement: 0.5 / 0.618 / 0.786
C wave extension:   1.0 / 1.272 / 1.618

```

### 11.3 Çıktı

```text
FIB_PASS, FIB_WATCH, FIB_FAIL, fib_score, fib_zone, fib_cluster

```

---

## 12. Zone Engine

### 12.1 Zone tipleri

```text
support_zone, resistance_zone, supply_zone, demand_zone,
range_high, range_low, value_area, fib_cluster_zone

```

### 12.2 Amaç

```text
Fiyat doğru yerde mi? Long için destek/demand bölgesinde miyiz?
Short için direnç/supply bölgesinde miyiz? Mid-range'de miyiz?

```

### 12.3 Mid-range kuralı (sayısallaştırıldı — v2.1 §11.3'ün netleşmiş hali)

```text
location_score >= market_location.good_location_min (70)  → GOOD_LOCATION
market_location.mid_range_min (40) <= score < 70             → MID_RANGE
score < 40                                                      → BAD_LOCATION

range içindeki pozisyon yüzdesi > max_mid_range_position_in_range_pct (0.35)
  ve score MID_RANGE bandındaysa → setup_confidence bir kademe düşer
  (confirmed → watch, watch → weak)

```

Mid-range işlem kalitesi düşüktür; bu artık bir his değil, sayısal bir
kademe düşürme kuralıdır.

---

## 13. Liquidity Sweep Engine

### 13.1 Okuyacağı durumlar

```text
previous high/low sweep, stop hunt, fake breakout, failed breakdown,
reclaim after sweep, liquidity grab

```

### 13.2 Örnek long reversal

```text
Fiyat eski dip altına iner, stopları toplar, range içine geri döner.
RSI bullish divergence + volume climax var.
Sonuç: REVERSAL_LONG_WATCH veya REVERSAL_LONG_CONFIRMED

```

---

## 14. Momentum / Divergence Engine

### 14.1 Okuyacağı sinyaller

```text
bullish/bearish RSI divergence, hidden divergence, MACD divergence,
momentum weakening, RSI extreme

```

### 14.2 Önemli bölgeler

```text
Wave 5 sonu, C wave sonu, range high/low,
liquidity sweep sonrası, fib cluster zone

```

### 14.3 Kural

Divergence tek başına işlem açtırmaz; setup kalitesini artırır
(Elliott gibi bir kanıt katmanıdır, §10.6).

---

## 15. Volume Validation Engine

### 15.1 Volume state

```text
VOLUME_CLIMAX, VOLUME_CONFIRMATION, VOLUME_WEAKENING, VOLUME_CONFLICT, VOLUME_NEUTRAL

```

### 15.2 Kullanım

```text
Wave 3 hacimli mi? Wave 5'te hacim zayıflıyor mu? Breakout hacimli mi?
Reversal mumunda hacim var mı? Fake breakout yüksek hacimle mi geldi?

```

---

## 16. VWAP / Anchored VWAP Engine

### 16.1 Okunacaklar

```text
VWAP üstü/altı, VWAP reclaim, VWAP rejection, VWAP deviation,
Anchored VWAP from major high/low/breakout point/volume climax candle

```

### 16.2 Kullanım

```text
VWAP üstünde tutunma → intraday long bias
VWAP altında retest failure → short scalp
VWAP'tan aşırı uzaklık → mean reversion watch

```

---

## 17. Exhaustion Score

### 17.1 Anlam (eşikler sayısal — §6 exhaustion.*)

```text
score <= downside_extreme_max (20)  → downside exhaustion / long reversal bölgesi
neutral_min (40) <= score <= neutral_max (60) → nötr
score >= upside_extreme_min (80)    → upside exhaustion / short reversal bölgesi

```

### 17.2 Kaynaklar

```text
RSI extreme, RSI divergence, EMA/ATR'dan uzaklık, son X mum getirisi,
volume climax, volatility shock, liquidity sweep

```

### 17.3 Kullanım

```text
Trend bearish + downside exhaustion + support
= short kovalamak tehlikeli, long reversal watch

```

---

## 18. Location Score

### 18.1 Sınıflar (sayısal — §12.3 ile aynı eşikler)

```text
GOOD_LOCATION (>= 70), MID_RANGE (40–69), BAD_LOCATION (< 40)

```

### 18.2 Kaynaklar

```text
fib zone, support/resistance, supply/demand, VWAP, range high/low,
liquidity sweep, ATR distance, structure invalidation distance

```

### 18.3 Örnek

```text
Short sinyal var ama fiyat major support dibinde:
BAD_LOCATION_FOR_SHORT

```

---

## 19. Setup Classifier

### 19.1 Setup tipleri

```text
TREND_LONG, TREND_SHORT, REVERSAL_LONG_WATCH, REVERSAL_SHORT_WATCH,
REVERSAL_LONG_CONFIRMED, REVERSAL_SHORT_CONFIRMED, SCALP_LONG, SCALP_SHORT,
RANGE_LONG, RANGE_SHORT, BREAKOUT_LONG, BREAKOUT_SHORT,
PULLBACK_LONG, PULLBACK_SHORT, NO_TRADE

```

### 19.2 Girdiler

```text
market_mode, market_structure, elliott_scenario (ağırlıklı, §10.6),
fib_validation, location_score, exhaustion_score, divergence,
volume_state, liquidity_sweep, trigger_state

```

### 19.3 Kural

Setup var = işlem açılır demek değildir. Setup sadece "fikir geçerli mi"
sorusuna cevap verir. Final karar Conflict Resolver + RiskGate'tedir.

---

## 20. Multi-Timeframe Alignment Matrix (yeni katman — v2.3)

Bu katman §4'teki "üst bağlam, alt giriş" kuralının çakışma durumlarını
**her zaman bir sonuca bağlayan** deterministik formülünü taşır.

### 20.1 Alignment Sınıfları

```text
FULLY_ALIGNED, PARTIALLY_ALIGNED, COUNTER_CONTEXT, CONFLICTING, NO_ALIGNMENT

```

### 20.2 Referans Tablo (örnekler — kod bu tabloyu lookup etmez, §20.3'teki formülü çalıştırır)

| 1D/1W | 4H | 1H | 15M | Sonuç |
|---|---|---|---|---|
| Bullish | Bullish | Bullish | Bullish | FULLY_ALIGNED |
| Bullish | Bullish | Bullish | Bearish | PARTIALLY_ALIGNED (pullback/scalp only) |
| Bullish | Bearish | Bearish | Bearish | COUNTER_CONTEXT_SHORT |
| Bullish | Bearish | Bullish | Bullish | PARTIALLY_ALIGNED_LONG |
| Bearish | Bearish | Bearish | Bearish | FULLY_ALIGNED |
| Bearish | Bullish | Bullish | Bullish | COUNTER_CONTEXT_LONG |
| Neutral | Bullish | Bullish | Bullish | PARTIALLY_ALIGNED |
| Neutral | Neutral | Bullish | Bullish | PARTIALLY_ALIGNED |
| Choppy | Any | Any | Any | NO_ALIGNMENT |

### 20.3 Fallback Formülü (kod yolu — her kombinasyon için çalışır)

```text
her timeframe'e yön skoru: Bullish=+1, Bearish=-1, Neutral=0, Choppy=0
weighted_score = Σ (yön_skoru[tf] × alignment.recency_weights[tf])
  # recency_weights = [0.40, 0.30, 0.20, 0.10]  (1D/1W, 4H, 1H, 15M)

eğer herhangi bir timeframe Choppy ise → NO_ALIGNMENT (override, başka kural çalışmaz)
|weighted_score| >= alignment.fully_aligned_min (0.70)        → FULLY_ALIGNED
alignment.partially_aligned_min (0.30) <= |weighted_score| < 0.70 → PARTIALLY_ALIGNED
  (üst timeframe(ler) alt timeframe(ler)e ters yönlüyse PARTIALLY_ALIGNED
   yerine COUNTER_CONTEXT olarak etiketlenir)
|weighted_score| < 0.30                                          → NO_ALIGNMENT

```

Referans tablo formülün test-case'idir: kod her zaman formülü çalıştırır,
tablo insan-okunur dokümantasyondur ve formülün üretmesi gereken sonuçları
doğrulamak için birim test verisi olarak kullanılır.

### 20.4 Kullanım

```text
FULLY_ALIGNED      → alignment_multiplier 1.00
PARTIALLY_ALIGNED  → alignment_multiplier 0.70
COUNTER_CONTEXT    → alignment_multiplier 0.35, sadece SCALP/INTRADAY (Agent Mode izin verirse)
CONFLICTING        → alignment_multiplier 0.00 → NO_TRADE
NO_ALIGNMENT        → alignment_multiplier 0.00 → NO_TRADE

```

---

## 21. Clean E-yAy Consensus Alignment

### 21.1 Okunacak mevcut alanlar

```text
technical direction score, consensus score, macro regime, risk appetite,
liquidity rotation, news/catalyst, derivatives risk, volatility risk,
correlation risk, mistake memory

```

### 21.2 Yeni anlam

```text
consensus score = directional pressure
score yüksek → bullish pressure (yön emri değil)
score düşük → bearish pressure
işlem yönünü setup classifier belirler

```

### 21.3 Alignment sınıfları (setup ↔ consensus arası — §20'deki timeframe-arası alignment'tan AYRI)

```text
ALIGNED, PARTIALLY_ALIGNED, CONFLICTING

```

Bu sınıflar **setup ile consensus arasındaki** uyumu ölçer; §20'deki
**timeframe'ler arası** alignment matrix ile karıştırılmaz. İki ayrı
girdi olarak Conflict Resolver'a (§28) gider.

### 21.4 Örnek

```text
Consensus bearish.
Elliott + Fib + RSI + Liquidity long reversal gösteriyor.
Bu otomatik çelişki değildir; reversal long zaten bearish baskının
sonunda aranır.

```

---

## 22. Trigger Engine

### 22.1 Trigger tipleri

```text
market structure break, higher low, lower high, bullish/bearish engulfing,
pin bar/rejection wick, breakout, retest failure,
VWAP reclaim/rejection, volume confirmation candle

```

### 22.2 Trigger state (eşik sayısal — §6 trigger.*)

```text
trigger_score >= trigger.confirmed_min (70) → TRIGGER_CONFIRMED
trigger_score < 70                            → TRIGGER_MISSING
(başarısız onay sinyali geldiyse)             → TRIGGER_FAILED

```

### 22.3 Kural

```text
Setup valid + trigger missing  = WATCH
Setup valid + trigger confirmed = trade candidate

```

---

## 23. Trade Profile Selector

### 23.1 Profiller

```text
SCALP, INTRADAY, TACTICAL, SWING, POSITION

```

### 23.2 Profile açıklamaları

```text
SCALP:    15M/5M/1M, yakın SL/TP, küçük size, kısa time stop
INTRADAY: 15M/1H, gün içi hedef, orta-küçük size
TACTICAL: 1H/4H, orta hedef/size, birkaç saat-gün
SWING:    4H/1D, geniş hedef, normal size, günler-haftalar
POSITION: 1D/1W güçlü uyum, uzun süreli, sadece yüksek confidence

```

### 23.3 Counter-context kuralı

Büyük timeframe ile çelişen küçük timeframe işlem yasak değildir ama
profile küçültülür:

```text
1D bullish, 15M short setup var
→ COUNTER_CONTEXT_SCALP_SHORT, size reduced (counter_context_multiplier=0.35),
  TP close, SL tight, time stop strict

```

---

## 24. SL / TP Planner

### 24.1 Stop-Loss Priority (sabit sıra, çakışmaz)

Long:

```text
1. Setup invalidation level
2. Last structural swing low
3. Elliott invalidation (varsa — yoksa bu adım atlanır)
4. Liquidity sweep low
5. ATR buffer
6. Max allowed stop distance (risk_reward.max_stop_distance_atr_mult)

```

Short için ayna simetrik (swing high, sweep high). SL bu mesafeyi aşarsa:

```text
NO_TRADE

```

### 24.2 Take-Profit Priority (profile bazlı, sabit sıra)

```text
SCALP:    nearest minor structure zone → VWAP/VWAP deviation mean
          → 15M range target → minor fib target
INTRADAY: 1H structure zone → VWAP/anchored VWAP → 4H nearest zone
          → fib retracement/extension
TACTICAL/SWING: 4H structure zone → fib target → Elliott projection
          → 1D zone → trailing target
POSITION: 1D/1W major zone → Elliott major projection → macro regime target
          → trailing stop

```

İlk sırada **geçerli** (fiyata pozitif mesafede, mantıklı) bir hedef
bulunursa o kullanılır, aşağı kademelere düşülmez.

### 24.3 RR Kontrolü

```text
RR < profile_min_rr (risk_reward.*_min_rr, §6) → NO_TRADE

```

### 24.4 Kâr yönetimi

```text
TP1 sonrası partial take profit
TP1 sonrası SL break-even opsiyonu
TP2 sonrası trailing stop
TP3 sadece kalan küçük pozisyon

```

---

## 25. Historical Edge Engine (Fuzzy Similarity)

### 25.1 Amaç

```text
Bu setup geçmişte çalışmış mı? Winrate kaç? Average R kaç?
Bu profile uygun mu? Scalp mi swing mi daha iyi çalışmış?

```

### 25.2 Similarity Weighting (`historical_similarity_weights`, §6 — toplam 1.00)

```text
setup_type 0.20, trade_profile 0.15, market_mode 0.12, timeframe_stack 0.12,
asset_class 0.08, elliott_scenario 0.08, fib_score_bucket 0.07,
divergence_state 0.06, volume_state 0.05, volatility_regime 0.04,
trigger_type 0.03

```

### 25.3 Similarity Score ve N Tanımı (sabitlendi — v2.2'deki belirsizlik kapatıldı)

```text
similarity_score = weighted sum of matched/near-matched features

similarity_score >= historical_edge.similarity_similar_min (0.70)
  → "similar" sayılır ve N (sample_count)'a dahil edilir
similarity_score >= historical_edge.similarity_strong_min (0.85)
  → "strong similar" (N_strong, N'in alt kümesi, sadece ek bilgi)

```

**N her zaman 0.70 eşiğine göre sayılır.** `N_strong` ayrıca raporlanır
ama `edge_confidence` hesabı her zaman ana N üzerinden yapılır.

### 25.4 Sample Count Güven Bandı

```text
N < 20            → observe-only
20 <= N < 50      → weak edge, sadece size azaltımı önerilebilir
50 <= N < 100     → usable edge
N >= 100          → strong edge

```

### 25.5 Output

```text
similar_sample_count, historical_winrate, average_R, median_R,
max_loss_R, max_drawdown, best_profile, recommended_size_modifier,
edge_confidence

```

### 25.6 Karar Etkisi

Historical Edge işlem açtırmaz; sadece:

```text
historical_edge_multiplier üretir (§27.2 sizing girdisi)
strong negative ise (winrate <= strong_negative_winrate_max VE
  avg_R <= strong_negative_avg_r_max VE N >= min_sample_usable)
  → NO_TRADE (sert blok — sadece size azaltımı değil)

```

### 25.7 Örnek

```text
Current setup: BTCUSD 4H C-wave ending, 1H bullish divergence,
  15M trigger confirmed, TACTICAL_LONG
Historical similar setups (>=0.70): 38
Winrate: 63%, Average R: +1.42R
Result: trade allowed, historical_edge_multiplier = weak_positive (0.80)

```

---

## 26. Agent Mode Permission Detayı

Conflict Resolver'a girmeden önce Agent Mode kararı netleşir (§5'in
özeti, çelişki çözümü §28'dedir):

```text
disabled profile + watch_disabled_profiles=true → WATCH_TRACKING
disabled profile + watch_disabled_profiles=false → NO_TRADE

```

---

## 27. Position Sizing Engine — Tek Formül (Weighted-Additive-Clamped)

### 27.1 Pür Çarpımsal Modelin Sorunu (düzeltildi)

8 çarpanın art arda çarpılması (örn. 0.70 × 0.70 × 0.50 × 0.35 × 0.50 ≈
0.043) sistemi hızla "ölü zon"a iter — orta seviyede 5-6 faktör bile
sonucu minimum eşiğin altına düşürür. v2.3 bu yüzden iki katmanlı model
kullanır.

### 27.2 Katman A — Hard Gates (çarpımsal, gerçekten sıfırlayabilir)

```text
hard_gate = dqs_multiplier × riskgate_multiplier × volatility_extreme_multiplier
# Bunlar GERÇEKTEN 0 olmalı: DQS_BAD, RiskGate KILL_SWITCH, EXTREME volatility
# Bu üç durum dışında hard_gate her zaman 1.00'dır.

```

### 27.3 Katman B — Soft Adjustments (ağırlıklı ortalama, sıfıra çökmez)

```text
soft_factor = Σ (weight[i] × multiplier[i])  ; Σ weight[i] = 1.00
  weights (position_sizing.soft_factor_weights, §6):
    alignment: 0.30, confidence: 0.25, historical_edge: 0.20,
    mistake_memory: 0.15, profile: 0.10

```

5 faktör orta seviyedeyken (~0.6-0.7) soft_factor ~0.55-0.65 civarında
kalır — çarpımsal modeldeki gibi 0.04'e düşmez.

### 27.4 Final Formül

```text
final_risk_pct = clamp(
    base_risk_pct × hard_gate × soft_factor,
    min = floor_risk_pct (0.00),
    max = max_risk_pct (1.00)
)

if hard_gate == 0:                         final_risk_pct = 0 → NO_TRADE
elif 0 < final_risk_pct < min_risk_pct (0.05): final_risk_pct = 0 → NO_TRADE
else:                                          final_risk_pct kullanılır

```

Historical Edge ile Position Sizing artık çakışmaz: Historical Edge
sadece `historical_edge_multiplier` üretir (girdi), final hesap tek
yerde (§27.4) yapılır.

### 27.5 Çarpan Tabloları

`sizing_multipliers` (§6) — alignment, confidence, historical_edge, dqs,
volatility, riskgate, mistake_memory için sabit eşlemeler. `CONFLICTING/
NO_ALIGNMENT = 0.00` ve `strong_negative = 0.00` soft_factor'e katkıda
sıfır verir ama soft_factor'ün tamamını sıfırlamaz (ağırlıklı ortalama);
gerçek sert bloklar zaten Katman A'da (§27.2) ve Historical Edge sert
blok kuralında (§25.6) ayrıca ele alınmıştır.

---

## 28. Conflict Resolver

### 28.1 Otorite Sıralaması (en yüksekten en düşüğe — hangi kural KAZANIR)

```text
1. Hard Safety            (KILL_SWITCH, DQS_BAD, PRICE_SANITY_FAIL, MAX_DAILY_LOSS, MAX_DRAWDOWN, EXTREME_EVENT_RISK)
2. Data Validity           (DQS state)
3. Agent Mode Permission   (profile enabled/disabled)
4. RiskGate                (PASS/CAUTION/NO_POSITION_INCREASE/KILL_SWITCH)
5. Position Management Rules (açık pozisyon ihlali varsa önce yönetilir)
6. Trigger Validity
7. SL / TP / RR Validity
8. Setup Validity
9. Historical Edge          (strong_negative → NO_TRADE; aksi halde sadece multiplier)
10. Position Sizing          (§27.4 final_risk_pct sonucu)
11. Alignment / Consensus    (directional pressure + timeframe alignment)
12. Elliott / Technical Evidence (en düşük — sadece girdi sağlar, asla tek başına bloklamaz/açmaz)

```

### 28.2 Hard Safety

```text
Her şeyi override eder. Sonuç her zaman BLOCKED.
Başka hiçbir katman bu kararı değiştiremez.

```

### 28.3 Agent Mode Permission

```text
SCALP setup + SCALP mode disabled
→ watch_disabled_profiles=true ise WATCH_TRACKING, değilse NO_TRADE

```

### 28.4 RiskGate

```text
KILL_SWITCH → BLOCKED
NO_POSITION_INCREASE → HOLD/NO_NEW_TRADE
RISK_REDUCE → SIZE_REDUCE veya HOLD
PASS → devam

Agent Mode: "Bu strateji şu an açık mı?" (yeni giriş filtresi, daha üstte
  çünkü RiskGate'e ulaşmadan girişi keser)
RiskGate:    "Bu işlem güvenli mi?" (RiskGate her zaman Agent Mode'un
  izin verdiği işlemi de bloklayabilir)

```

### 28.5 Log Sırası vs Otorite Sırası (v2.2'deki belirsizlik kapatıldı)

İki ayrı liste, asla birleştirilmez:

```text
authority_order (§28.1):       hangi kural KAZANIR — final_action'ı
  belirleyen, en yüksek otoriteli (1'e yakın) kural.
conflict_resolution_path:        pipeline'ın GERÇEKTEN ÇALIŞMA SIRASI
  (kronolojik): data → mtf → market_mode → structure → elliott → fib →
  zone → liquidity → momentum → volume → vwap → exhaustion → location →
  setup_classifier → alignment_matrix → consensus → trigger →
  trade_profile → agent_mode → sl_tp_planner → historical_edge →
  position_sizing → conflict_resolver → risk_gate → final_decision.

```

`blocked_by` listesi her zaman **authority_order**'a göre sıralanır (en
yüksek otoriteli blok ilk sırada); `conflict_resolution_path` pipeline'ın
kronolojik yürütme izidir. Bu iki alan asla tek listeye birleştirilmez.

---

## 29. DQS_DEGRADED Karar Matrisi

```text
DQS_OK        >= dqs.ok_min (0.80)
DQS_DEGRADED  = dqs.degraded_min..ok_min (0.60–0.79)
DQS_BAD       < dqs.bad_below (0.60)

```

| Durum | Aksiyon |
|---|---|
| DQS_BAD | BLOCKED |
| DQS_DEGRADED + SCALP | NO_TRADE |
| DQS_DEGRADED + INTRADAY | WATCH veya 0.35x size |
| DQS_DEGRADED + TACTICAL | 0.35x size max |
| DQS_DEGRADED + SWING | WATCH unless confirmation strong (trigger_score >= confirmed_min VE setup_confidence >= confirmed_min) |
| DQS_DEGRADED + POSITION | WATCH |
| DQS_DEGRADED + RiskGate caution | NO_TRADE |

---

## 30. RiskGate

### 30.1 Bloklayıcı durumlar

```text
KILL_SWITCH, NO_POSITION_INCREASE, RISK_REDUCE, DQS_LOW, MAX_DAILY_LOSS,
MAX_DRAWDOWN, EXTREME_EVENT_RISK, CORRELATION_LIMIT, PRICE_SANITY_FAIL

```

### 30.2 Kural

```text
Elliott pass olsa bile, Fib pass olsa bile, RSI divergence olsa bile,
Trigger confirmed olsa bile, Historical edge iyi olsa bile,
Agent mode aktif olsa bile — RiskGate kapalıysa işlem açılmaz.

```

---

## 31. Paper Trading Engine

```text
PAPER_ONLY, NO_REAL_EXECUTION, NO_BROKER_ORDER

```

Görevler: position open/close, partial take profit, SL/TP simulation,
time-stop, break-even SL move, trailing stop, PnL calculation, trade
journal write.

---

## 32. Position Management Engine

### 32.1 İzlenecekler

```text
TP1/TP2 reached? SL hit? time stop expired? setup invalidated?
opposite signal appeared? RiskGate changed? volatility expanded?
DQS degraded? agent mode changed?

```

### 32.2 Aksiyonlar

```text
HOLD, CLOSE, PARTIAL_CLOSE, MOVE_SL_TO_BREAK_EVEN, TRAIL_SL, REDUCE_SIZE

```

### 32.3 Agent mode değişirse

```text
Scalp mode kapatıldı, açık scalp işlemler var.
→ new scalp entries disabled (hemen)
→ existing scalp positions managed by risk rules
→ close_disabled_profile_positions=true ise: kapatma RiskGate onayından
  geçmeden tetiklenmez (close_requires_riskgate_pass, §6)

```

Pozisyon kapatma her zaman bir risk kararıdır; config flag tek başına
yeterli değildir.

---

## 33. Trade Journal Engine

```text
trade_id, asset, entry_time, exit_time, entry_price, exit_price, side,
size, timeframe_stack, setup_type, trade_profile, agent_mode,
elliott_scenario, fib_score, rsi_divergence, volume_state,
liquidity_state, market_structure_state, trigger_type, entry, SL,
TP1/TP2/TP3, RR, result_R, PnL, MAE, MFE, exit_reason, mistake_tags

```

---

## 34. Post-Trade Learning Engine

### 34.1 Kârlı işlemlerden öğrenme

```text
Hangi setup çalıştı? Hangi timeframe stack çalıştı? Hangi agent mode
aktifti? TP erken mi alındı? Trailing daha iyi olur muydu?

```

### 34.2 Zararlı işlemlerden öğrenme — Mistake tag örnekleri

```text
BAD_LOCATION, LATE_ENTRY, NO_TRIGGER, WEAK_VOLUME, FALSE_BREAKOUT,
WRONG_TIMEFRAME_ALIGNMENT, COUNTER_CONTEXT_TOO_LARGE, STOP_TOO_TIGHT,
STOP_TOO_WIDE, TP_TOO_FAR, LOW_DQS, HIGH_VOLATILITY, NEWS_EVENT_RISK,
RISK_GATE_TOO_LOOSE, ELLIOTT_SCENARIO_FAILED, DISABLED_MODE_OVERRIDE_ERROR

```

---

## 35. Missed Opportunity Engine

### 35.1 Amaç

```text
WATCH verilen setup sonradan TP'ye gitti mi? NO_TRADE verilen setup
aslında çalıştı mı? RiskGate yüzünden açılmayan işlem kâr etti mi?
Agent mode kapalı olduğu için kaçırılan fırsat var mı?

```

### 35.2 Tracking Başlatma Koşulları

```text
setup valid + SL/TP hesaplanabilir + RR valid +
trigger confirmed veya nearly confirmed (>= trigger.confirmed_min - 10) +
(RiskGate pass VEYA Agent Mode disabled nedeniyle açılmadı)

```

Sadece fiyatın gitmesi missed opportunity sayılmaz.

### 35.3 TTL (`missed_opportunity.watch_ttl_bars`, §6)

```text
SCALP: 12 bars, INTRADAY: 24, TACTICAL: 48, SWING: 80, POSITION: 120
max_tracking_days: 30 (hard cap)

```

### 35.4 Tracking Stop

```text
TTL expired, setup invalidated, SL level touched,
opposite setup confirmed, DQS_BAD, asset removed

```

### 35.5 Missed Opportunity Sayılması

```text
simulated path TP1'e SL'den önce ulaşır VE result >= min_missed_r (1.0R)

```

### 35.6 Agent mode nedeniyle kaçan fırsat

```text
missed_reason: SCALP_DISABLED
lesson: Scalp mode kapalıyken kaçan fırsat raporlandı.
Config otomatik değiştirilmez; sadece öneri üretilir, kullanıcıya raporlanır.

```

---

## 36. Mistake Memory

### 36.1 Yasak davranış

```text
Son 3 işlem kazandı → size 3x   [YASAK]

```

### 36.2 Doğru yaklaşım

```text
Yeterli örnek sayısı + istatistiksel anlamlılık varsa,
sadece threshold/size/filter üzerinde küçük ayar öner.

```

### 36.3 Kullanım

```text
Setup son 50 örnekte kötü çalışıyorsa: size reduce (mistake_memory.CAUTION/AVOID_SIMILAR)
Setup son 100 örnekte iyi çalışıyorsa: normal size allowed (CLEAN)
Düşük örnek sayısında: observe-only

```

---

## 37. Final Decision Engine

### 37.1 Final action tipleri

```text
OPEN_LONG_PAPER, OPEN_SHORT_PAPER, WATCH_LONG, WATCH_SHORT, NO_TRADE,
BLOCKED, MANAGE_EXISTING_POSITION, CLOSE_POSITION, PARTIAL_CLOSE,
MOVE_SL, TRAIL_SL, REDUCE_SIZE

```

### 37.2 Final Decision Önceliği

```text
1. BLOCKED
2. CLOSE / MANAGE EXISTING POSITION
3. NO_TRADE
4. WATCH
5. OPEN_PAPER

```

### 37.3 Final Decision Tablosu

| Durum | Final |
|---|---|
| DQS_BAD | BLOCKED |
| KILL_SWITCH | BLOCKED |
| Agent profile disabled | NO_TRADE veya WATCH_TRACKING |
| RiskGate NO_POSITION_INCREASE | NO_TRADE |
| Setup weak (`confidence < setup_confidence.weak_below`) | NO_TRADE |
| Trigger missing | WATCH |
| RR invalid | NO_TRADE |
| Historical edge strong negative | NO_TRADE |
| Historical edge weak negative | SIZE_REDUCE / WATCH |
| DQS_DEGRADED + scalp | NO_TRADE |
| DQS_DEGRADED + tactical strong setup | SIZE_REDUCE |
| Alignment FULLY_ALIGNED + trigger confirmed + RiskGate pass | OPEN_PAPER |
| COUNTER_CONTEXT + mode allowed | SCALP/INTRADAY reduced size |
| COUNTER_CONTEXT + mode disabled | NO_TRADE |
| Alignment CONFLICTING/NO_ALIGNMENT | NO_TRADE |

### 37.4 Trade açma koşulu

```text
DQS valid, market mode valid, setup valid, alignment valid
  (fallback formülü dahil her durumda sonuçlanır), agent mode active,
location acceptable, trigger confirmed, SL/TP/RR valid,
historical edge acceptable, position size valid (> min_risk_pct),
RiskGate pass

```

### 37.5 Watch koşulu

```text
setup valid + trigger missing
veya setup valid + location incomplete (MID_RANGE üstü eşik aşımı)
veya setup valid + historical sample düşük (N<20)
veya setup valid + trade profile disabled ama watch_tracking aktif

```

### 37.6 No trade koşulu

```text
setup weak, location bad, RR invalid, data weak, market choppy
(NO_ALIGNMENT), trigger failed, trade profile disabled
(watch_tracking kapalıyken), strategy type disabled

```

### 37.7 Blocked koşulu

```text
RiskGate hard block, DQS bad, kill switch, daily loss,
correlation limit, price sanity fail

```

### 37.8 Output Şeması

```json
{
  "candidate_action": "OPEN_SHORT_PAPER",
  "final_action": "NO_TRADE",
  "blocked_by": ["BAD_LOCATION_FOR_SHORT", "SCALP_DISABLED"],
  "reduced_by": [],
  "authority_order_applied": ["agent_mode_permission", "setup_validity"],
  "conflict_resolution_path": [
    "data_valid", "elliott_no_valid_count", "setup_classifier_detected_scalp_short",
    "alignment_partially_aligned", "trigger_confirmed", "trade_profile_selected_SCALP",
    "agent_mode_rejected_SCALP", "watch_tracking_enabled"
  ],
  "active_thresholds": {"setup_confidence.weak_below": 55, "trigger.confirmed_min": 70},
  "sizing_multipliers": {"hard_gate": 1.00, "soft_factor": 0.0},
  "mode_filter_result": {"passed": false, "reason": "SCALP_DISABLED"},
  "risk_gate_result": "PASS",
  "historical_edge_result": {"sample_count": 0, "edge_confidence": "observe_only"},
  "missed_opportunity_tracking": true
}
```

`blocked_by` her zaman otorite sırasına göre, `conflict_resolution_path`
her zaman kronolojik sırada doldurulur (§28.5).

---

## 38. Dashboard Architecture

### 38.1 Layer 0 — Decision Cockpit

```text
Asset, Action, Setup type, Trade profile, Agent mode, Risk state,
Entry, SL, TP, Size, Reason, Trigger status, Historical edge,
Alignment class, blocked_by (otorite sıralı)

```

Örnek:

```text
BTCUSD
Action: WATCH_LONG
Setup: REVERSAL_LONG_WATCH
Profile: TACTICAL
Agent Mode: TACTICAL enabled, SCALP disabled
Alignment: PARTIALLY_ALIGNED
Elliott: C wave ending possible (confidence 62 → orta ağırlık)
Fib: PASS
RSI div: PASS
Volume: WATCH
Trigger: MISSING
RiskGate: PASS
Historical edge: N=14, observe-only

```

### 38.2 Layer 1 — Market Overview

```text
Asset list, Setup list, Active agent modes, Risk status, DQS,
Market mode, Regime, Liquidity rotation, Open position summary

```

### 38.3 Layer 2 — Labs

```text
Elliott Lab, Setup Lab, Risk Lab, Liquidity Lab, News/Catalyst Lab,
Position Lab, Learning Lab, Agent Mode Lab, Conflict Resolver Lab (yeni)

```

### 38.4 Layer 3 — Raw Trace

```text
raw scores, scenario list, feature values, audit trail, decision reasons,
historical matches, learning tags, mode filter results,
authority_order_applied, conflict_resolution_path, active_thresholds

```

---

## 39. API / Contract Output

```text
symbol, timeframe_stack, action, candidate_action, setup_type,
setup_confidence, trade_profile, agent_mode_config, mode_filter_result,
market_mode, trend_score, exhaustion_score, location_score,
confirmation_score, alignment_class, alignment_weighted_score,
elliott_primary_scenario, elliott_alternatives, elliott_confidence,
elliott_invalidation, elliott_target_zone, fib_score, fib_zone,
rsi_divergence, volume_state, liquidity_state, vwap_state,
trigger_status, entry_price, stop_loss, take_profit_1, take_profit_2,
take_profit_3, risk_reward, position_size, hard_gate, soft_factor,
historical_winrate, historical_avg_R, historical_sample_count,
historical_similarity_threshold_used, risk_gate_state,
authority_order_applied, conflict_resolution_path, active_thresholds,
decision_reasons, paper_safe, no_execution

```

---

## 40. Agent Mode API / Config

### 40.1 Config alanları

```text
enabled_trade_profiles, disabled_trade_profiles, focus_mode,
allow_scalp, allow_intraday, allow_tactical, allow_swing, allow_position,
allow_counter_context_trades, allow_reversal_trades,
allow_trend_follow_trades, allow_range_trades, allow_breakout_trades,
watch_disabled_profiles, close_disabled_profile_positions,
close_requires_riskgate_pass

```

### 40.2 Örnek config

```json
{
  "enabled_trade_profiles": ["INTRADAY", "TACTICAL", "SWING"],
  "disabled_trade_profiles": ["SCALP", "POSITION"],
  "focus_mode": "TACTICAL",
  "allow_counter_context_trades": false,
  "allow_reversal_trades": true,
  "allow_trend_follow_trades": true,
  "allow_range_trades": true,
  "allow_breakout_trades": true,
  "watch_disabled_profiles": true,
  "close_disabled_profile_positions": false,
  "close_requires_riskgate_pass": true
}
```

### 40.3 Mode filter result

```json
{
  "mode_filter_result": {
    "passed": false,
    "blocked_reason": "SCALP mode disabled",
    "candidate_profile": "SCALP",
    "focus_mode": "TACTICAL",
    "watch_tracking_enabled": true
  }
}
```

---

## 41. Önerilen Paket Yapısı

```text
packages/data/            (ingestion, quality, snapshot, types)
packages/market/          (mode, structure, zones, liquidity, vwap, volatility)
packages/elliott/         (models, pivots, wave_rules, fib_validation, scenario_builder, scoring, engine)
packages/momentum/        (divergence, rsi, macd)
packages/volume/          (validation, climax)
packages/alignment/        (matrix, fallback_formula)        # YENİ
packages/setup/           (models, classifier, scoring, trigger, trade_profile, planner)
packages/mode/             (config, filter, policy)
packages/policy/            (threshold_config_loader)          # YENİ
packages/decision/         (engine, matrix, finalizer, conflict_resolver)  # conflict_resolver YENİ
packages/risk/              (gate, sizing, correlation, drawdown)
packages/paper/             (state, execution, position, lifecycle, journal)
packages/learning/          (post_trade, missed_opportunity, historical_edge, mistake_memory, reports)

apps/api/routers/
  decision.py, paper_trading.py, learning.py, elliott.py, setup.py, agent_mode.py

config/
  policy_v2.3.yaml          # YENİ — tüm sayısal eşikler

contracts/
  openapi.yaml

apps/web/components/
  cockpit/, labs/, positions/, learning/, agent-mode/

```

---

## 42. Sprint Plan

```text
Sprint 1  — Core Data + DQS + Snapshot
Sprint 2  — Market Mode + Structure + Zones
Sprint 3  — Pivot + Elliott Scenario Engine (opsiyonel-evidence kuralıyla)
Sprint 4  — Fib + RSI + Volume + Liquidity + VWAP
Sprint 5  — Setup Classifier + Exhaustion/Location Score
Sprint 6  — Multi-Timeframe Alignment Matrix + fallback formülü     (YENİ sprint)
Sprint 7  — Trigger + Trade Profile + Agent Mode Control
Sprint 8  — Policy/Threshold Config + Conflict Resolver (otorite sırası)  (YENİ sprint)
Sprint 9  — SL/TP Planner (sabit öncelik) + Position Sizing (hard-gate × soft-factor)
Sprint 10 — Historical Edge Engine (fuzzy similarity, sabit N tanımı)
Sprint 11 — RiskGate + Paper Trading
Sprint 12 — Position Management (RiskGate onaylı kapatma dahil)
Sprint 13 — Learning Engine (journal, mistake tags, missed opportunity + TTL)
Sprint 14 — Dashboard (Layer 0-3 + Conflict Resolver Lab)

```

---

## 43. Son Ana İlke

Clean E-yAy v2.3'ün ana mantığı:

```text
Piyasa hangi fazda?
Hangi Elliott senaryosu güçlü (varsa — zorunlu değil)?
Fiyat doğru bölgede mi (sayısal eşikle)?
Momentum uyumsuzluğu var mı?
Hacim destekliyor mu?
Likidite süpürülmüş mü?
Timeframe'ler birbiriyle uyumlu mu (fallback formülü her zaman bir cevap verir)?
Setup trend mi, reversal mı, scalp mi?
Bu işlem modu şu an aktif mi?
Trigger geldi mi?
Geçmişte bu setup çalışmış mı (fuzzy similarity, sabit N)?
Hangi kural hangi kuralı geçersiz kılıyor (otorite sırası)?
Risk buna izin veriyor mu?
SL/TP/size mantıklı mı (tek formül, çarpımsal çöküş yok)?

```

Sonra karar:

```text
OPEN_LONG_PAPER, OPEN_SHORT_PAPER, WATCH_LONG, WATCH_SHORT, NO_TRADE,
BLOCKED, MANAGE_EXISTING_POSITION

```

Clean E-yAy v2.3, tek skorla işlem açan sistem değildir; piyasayı bağlam,
yapı, setup, aktif strateji modu, risk ve geçmiş performans üzerinden
**deterministik, izlenebilir ve replay edilebilir** şekilde okuyan çok
katmanlı trading intelligence sistemidir. v2.1'in tüm zenginliği
korunmuş, v2.2'nin kapattığı boşluklar bu belgede inline hale getirilmiş
ve v2.2'nin kendi içinde bıraktığı 5 ek boşluk (alignment fallback,
sizing çöküşü, log/karar sırası karışıklığı, N tanım belirsizliği,
RiskGate'siz pozisyon kapatma) ayrıca kapatılmıştır.
