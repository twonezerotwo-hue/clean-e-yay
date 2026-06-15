# E-yAy Clean — Technical Analysis Mimarisi (Final)

> Owner tarafından verilen build incili. Multi-timeframe teknik analizin mevcut
> ARCHITECTURE.md omurgasına nasıl oturacağını tanımlar. Ayrı bir
> `packages/technical` monoliti **kurulmaz**. Teknik analiz var olan paketlere
> yeniden yerleştirilir. Felsefe: *eski sistemin zekasını taşı, dağınıklığını taşıma.*

İlerleme durumu için bkz. [`TECHNICAL_ARCHITECTURE_PROGRESS.md`](TECHNICAL_ARCHITECTURE_PROGRESS.md).

---

## 0. Prime directive

1. `packages/technical` monoliti KURULMAZ. Teknik mantık var olan paketlere dağıtılır.
2. İş yıkıcı değil, eklemeli (additive).
3. Build sırası ARCHITECTURE.md'deki T1 → T2 planıyla aynı.
4. PAPER_SAFE / NO_EXECUTION mutlak kalır.
5. RiskGate tek nihai otoritedir; teknik modül trade açmaz, size artırmaz.
6. Contract-first: her yeni model önce `contracts/openapi.yaml`'a girer.

### Çekirdek kural
Her teknik gösterge per (symbol, closed-candle timeframe) hesaplanır.
TechnicalAgent her timeframe için tek bir yapılandırılmış görüş üretir.
Consensus, timeframe'leri ve agent'ları birleştirir.
Hiçbir tek "aggregated_technical_score" tüm stratejileri temsil edemez.

---

## 1. Pipeline'daki yer

```
Market Snapshot
   → Feature Builder ........ [per-TF technical result]
   → Specialist Agents (TechnicalAgent [YENİ] + Macro/Risk/News/Flow)
   → Consensus .............. [TF + agent birleştirme]
   → Decision Orchestrator .. [deterministik aksiyon]
   → Risk Gate .............. [cost + R:R + sizing + cap — tek otorite]
   → Paper Trading
   → Learning ............... [calibration + walkforward + outcomes]
   → Rebalance Proposal → Owner Approval
```

## 2. Katman sorumlulukları ve repodaki yeri

| Katman | Yer | Durum | Görev |
| --- | --- | --- | --- |
| Indicator math (multi-TF, closed-candle) | `packages/data/providers/technical/` | GENİŞLET | RSI/MACD/EMA/ATR/ADX/fib/levels/patterns |
| Per-TF technical feature | `packages/data` feature builder | YENİ | indikatörleri TechnicalTimeframeResult'a paketler |
| Teknik yorum / bias | `packages/agent/technical_agent.py` | YENİ | tek agent görüşü (ALLOW/CAUTION/ABSTAIN + invalidation) |
| Piyasa rejimi (macro) | `packages/regime` | VAR, TÜKET | RISK_ON/DEFENSIVE/CRISIS global filtre |
| TF + agent birleştirme | `packages/consensus` | TAMAMLA | direction/strength/agreement + alignment |
| Deterministik karar | `packages/decision` | TAMAMLA | NO_TRADE/WATCH/SCOUT_ALLOWED/... |
| Cost + R:R + sizing + cap | `packages/risk` | GENİŞLET | maliyet net edge, R:R kapısı, size cap; RiskGate final |
| Paper lifecycle | `packages/paper` | VAR | execution_sim, time-stop, manual_queue |
| Validation / kalibrasyon | `packages/learning` | VAR, BAĞLA | walkforward, calibration, outcomes |
| Veri kalitesi (DQS) | `packages/data/quality` | VAR, TÜKET | freshness + warm-up + degraded |

**Önemli ayrım:** macro regime (`packages/regime`, fiyat-dışı: DXY/VIX/HYG) ile per-TF
volatility regime (fiyat-türevli: ATR percentile/BB width) farklı kapsamlardır. İkisi de yaşar.

---

## 3. Timeframe modeli (first-class) ve strateji eşlemesi

| TF | Rol | Risk çarpanı | Strateji etiketi |
|----|-----|--------------|------------------|
| 15m | scout / news shock | ×0.25 | scalp |
| 1h | intraday confirm | ×0.50 | intraday |
| 4h | tactical setup | ×1.00 | intraday/swing tetik |
| 1d | swing bias | ×1.00 | swing |
| 1w | strategic view | TRADE AÇMAZ | sadece bias/filtre |

**Değişmez kurallar:**
- Üst TF, alt TF'e veto/scale-down uygular. ASLA scale-up yok.
- timeframe_risk çarpanları yalnızca küçültür (≤1.0). RiskGate bypass edilemez.
- Global risk (DQS veto, KILL_SWITCH, daily-loss/max-DD halt) TF ayrımı yapmaz.
- 1w yön/filtre verir, kendi başına giriş üretmez.

### Strateji = giriş TF + üst TF filtresi
- **Swing** (giriş 1d): sinyal 1d; 4h+1h teyit; 1w bias filtresi; 15m gürültü.
- **Intraday** (giriş 1h/4h): sinyal 1h/4h; 1d bias; 15m timing; üst TF veto.
- **Scalp** (giriş 15m): sinyal 15m; 1h/4h veto; 1d/1w makro filtre; size ×0.25.

### Countertrend (koşullu)
```
is_countertrend = sign(higher_tf_bias) != sign(lower_tf_signal)
```
Sadece bu koşul sağlanınca countertrend etiketlenir. Üst ve alt TF aynı yöndeyse
trend-aligned setup'tır, countertrend değil.
```
action = SCOUT_ALLOWED veya CONFIRMATION_REQUIRED (asla otomatik full giriş)
size   = üst TF çarpanı × ek countertrend cap
manual_ready_required = true
```

### Bias ve alignment (NEUTRAL dahil)
```
bias = BULLISH if score > bull_cut ; BEARISH if score < bear_cut ; else NEUTRAL
alignment_score = TF biaslarının ağırlıklı uyumu (NEUTRAL'lar uyumu seyreltir)
alignment_status in {ALIGNED, PARTIAL, COUNTERTREND, CONFLICTED}
```

---

## 4. Per-TF teknik hesaplama (modüller = fonksiyon, paket değil)

Hepsi `packages/data/providers/technical/` altında **saf fonksiyon**.

- **4.1 Closed-candle policy** (lookahead engeli): tek `as_of_timestamp`; tüm
  indikatörler yalnız kapanmış mumları kullanır.
- **4.2 Indicators:** ema/ema_series/rsi/macd/atr (mevcut) + adx+DI, atr_percent,
  swing pivots, vwap (yalnız intraday TF; 1d/1w'de üretilmez).
- **4.3 Levels:** support/resistance (swing + hacim düğümü), atr, atr_percent,
  stop_reference, target_reference.
- **4.4 Scoring vs confirmations (çift sayım yok):** scoring = "YÖN ve GÜÇ"
  (trend_structure + momentum + location + volume); confirmations = "TETİKLENDİ Mİ"
  (candle close, trigger, timing). EMA/volume büyüklüğü yalnız scoring'de sayılır.
- **4.5 Fibonacci / reversal / patterns (stateful):** fib levels/zone/score;
  reversal (double_bottom, RSI/MACD divergence); patterns (active_patterns, bias).
- **4.6 Per-TF volatility regime + trend strength:** TRENDING/RANGING/SQUEEZE/EXPANSION
  (atr_pct, bb_width); ADX bandı → trend gerçek mi. `ADX<20` → trend-follow zayıflar,
  level/reversal ağırlık kazanır; SQUEEZE → breakout teyidi beklenir.
- **4.7 Confluence:** per-TF (feature builder) + cross-TF (consensus) ayrı.
- **4.8 Quality/warm-up (DQS tüket):** eksik veri = diagnostic; ASLA fake neutral.
  Eksik M15, D1/H4/H1'i çökertmez (graceful degradation).

---

## 5. Kanonik modeller (contract-first)

```
TechnicalTimeframeResult: timeframe, data_quality (indicator_quality), score_overview
  (direction_score, strength_score), key_levels, confirmation_signals, fibonacci_analysis,
  reversal_signals, chart_pattern_analysis, trend_strength, volatility_regime,
  confluence_zones (per-TF), timeframe_summary (bias, evidence, warnings)

TechnicalAgentOutput: agent="technical", per_timeframe {m15,h1,h4,d1,w1},
  stance: ALLOW/CAUTION/ABSTAIN/DEGRADED, direction_score, strength_score,
  used_observations, invalidation, missing_data

ConsensusSnapshot: asset, per_timeframe_bias (+NEUTRAL), alignment_status/alignment_score,
  cross_timeframe_confluence, direction_score, strength_score, agreement_score,
  confirmed_count/pending_count/blocking_count, evidence

AgentDecision: action (NO_TRADE|WATCH|SCOUT_ALLOWED|CONFIRMATION_REQUIRED|RISK_REDUCE|
  KILL_SWITCH), entry_timeframe, confidence/reason, supporting_agents/blocking_agents,
  required_confirmations, risk_gate_required=true
```
Dashboard, `decision/cockpit.py` çıktısını okur; yeni cockpit yazılmaz.

---

## 6. Değişmez kurallar ve guard testleri

| Kural | Test |
|-------|------|
| closed-candle only | test_no_open_candle_indicators |
| tek global skor yok | test_no_single_score_for_all_strategies |
| countertrend koşullu | test_countertrend_score_is_conditional |
| eksik veri = diagnostic | test_missing_data_not_neutral |
| frontend teknik hesap yok | test_no_frontend_technical_math |
| AI size artırmaz | test_no_ai_size_boost |
| tek RiskGate | test_single_riskgate |
| teknik modül trade açmaz | test_no_technical_module_trade_execution |
| üst TF alt TF'i scale-up etmez | test_upper_tf_only_scales_down |
| determinism | test_same_closed_input_same_output |
| kötü R:R blocklanır | test_bad_rr_blocks_entry |
| scalp maliyetten düşükse red | test_scalp_below_cost_blocked |

---

## 7. Config eklemeleri

```yaml
# config/thresholds.yaml
technical:
  bias_cuts: { bull: 60, bear: 40 }
  adx_trend_min: 20
  warmup_min_bars: { rsi: 30, macd: 60, ema200: 220, atr: 30 }

# config/weights_v1.yaml  (PRIOR; learning ile kalibre edilir)
tf_weights:
  swing:    { d1: 0.50, h4: 0.35, h1: 0.15, m15: 0.00 }
  intraday: { d1: 0.15, h4: 0.35, h1: 0.35, m15: 0.15 }
  scalp:    { d1: 0.00, h4: 0.15, h1: 0.35, m15: 0.50 }

# config/risk_policy.yaml
tf_risk_multiplier: { m15: 0.25, h1: 0.50, h4: 1.0, d1: 1.0, w1: 0.0 }
costs: { taker_fee_bps: 10, est_spread_bps: 2, est_slippage_bps: 3 }
min_net_edge_bps: 20
min_rr: 1.5
```
> Not (clean-e-yay): config dosyaları versiyonlu — `thresholds_v1.0.yaml`,
> `weights_v1.0.yaml`. `technical:` ve `decision:` blokları `thresholds_v1.0.yaml`'a
> eklendi; `timeframe_risk` zaten orada.

---

## 8. Validation / kalibrasyon (learning ile)
- Aynı closed-candle pipeline ile historical replay (`packages/data/backtest`).
- Outcome'lar `packages/learning/outcomes` ile toplanır.
- Skor kovası → hit-rate, expectancy (`calibration.py`).
- tf_weights PRIOR olarak başlar, auto_weight_trainer + walkforward ile ayarlanır.
- Kural: ağırlıklara, kalibrasyon onları doğrulayana kadar güvenme.

---

## 9. Build sırası (additive, T1 → T2)

1. (T1) data/providers/technical genişlet: closed-candle + multi-TF + adx/fib/levels/patterns
2. (T1) feature builder: TechnicalTimeframeResult + warm-up/quality
3. (T2) `packages/agent/technical_agent.py`: per-TF görüş + bias + invalidation
4. (T2) `packages/consensus` tamamla: TF+agent birleştirme, alignment, cross-TF confluence, NEUTRAL, countertrend
5. (T2) `packages/decision` tamamla: entry_timeframe + aksiyon enum
6. (T2) `packages/risk` genişlet: costs + risk_reward + tf cap
7. contracts/openapi.yaml + codegen + minimal status/TimeframeMatrixPanel
8. learning bağlama: replay → outcomes → calibration → auto_weight
9. controlled activation (shadow_mode önce; affect_decision: false → izle → sonra true)

**Her adım sonu:** `make lint && make test`. **Onay olmadan push yok.**

---

## 10. Net çekirdek kural

Technical analysis is NOT a package. It is a capability that flows through:
data/providers/technical → TechnicalAgent → consensus → decision → RiskGate
(single final authority) → paper → learning. No monolith. No single aggregated
score for all strategies. Upper timeframe only scales down. RiskGate is final.
Owner approves.
