# TASK RESULT

Date: 2026-06-12
Task: P0 intelligence parity (kısmî) — gerçek rotation engine + news/calendar
      sağlayıcılarının pipeline'a entegrasyonu (WIP recovery)
Status: completed (core); kalan kapsam SKIPPED/NEXT olarak işaretlendi

## WIP recovery

Önceki session token bitince yarım kalmıştı. Bulunan durum:
- `providers/rotation/engine.py` yazılmış (legacy momentum/oran portu) ve
  derlenebilir; **provider'a bağlı değildi** — `rotation/__init__.py` hâlâ
  eski hash-mock `get_rotation()` kullanıyordu. Kaldığı tam nokta buydu.
- News (`__init__/rss/classify/fixtures`) ve calendar (`__init__` + YAML)
  sağlayıcıları tamamdı ve derleniyordu, fakat pipeline `provider_status`'a
  ve unavailable-warning'lerine bağlı değildi.

## Ne yapıldı

1. **Rotation engine → provider wiring** (kaldığı yer): `get_rotation()`
   yeniden yazıldı; Clean OHLCV cache'inden (1d) rotasyon sembollerinin
   kapanış serilerini toplar, `engine.compute()` çağırır, `RotationView`
   üretir. Veri yetersiz → `status="UNAVAILABLE"`, nötr 50, provider DEGRADED;
   mock skor YOK. News/calendar pattern'iyle aynı provider status tracker.
2. **SPY → SP500 eşlemesi**: engine'in "SPY" slotu Clean registry'sinde
   zaten var olan `SP500` (^GSPC) OHLCV'sine eşlendi → hisse (risk-on) bacağı
   canlıda aktif (universe expansion değil, mevcut veriyi doğru bağlama).
3. **Pipeline entegrasyonu**: `provider_status`'a news/geo_news/calendar/
   rotation eklendi; `news_unavailable` / `calendar_unavailable` /
   `rotation_unavailable` warning'leri (DATA_POLICY — veri yoksa mock değil
   açık uyarı).
4. **Consensus safety**: rotation `UNAVAILABLE` ise `quantum` modülü `raw`'dan
   düşürülür; ağırlığı mevcut `_redistribute` ile diğer modüllere dağıtılır
   (chart_pattern ile aynı desen). Mock rotasyon skoru artık karar zincirine
   giremez.
5. **Testler**: `tests/unit/test_rotation.py` (5 test) — deterministik skor,
   yetersiz veri → UNAVAILABLE, identical-returns guard, fixture provider OK,
   consensus quantum redistribute.

## Files changed

- `packages/data/providers/rotation/__init__.py` — hash-mock → gerçek engine
  wiring + provider status tracker (rewrite).
- `packages/data/providers/rotation/engine.py` — WIP'ten gelen motor;
  ROTATION_SYMBOLS "SPY"→"SP500" düzeltmesi.
- `packages/data/ingestion/pipeline.py` — provider_status (news/geo_news/
  calendar/rotation) + unavailable warning'leri.
- `packages/consensus/engine.py` — rotation UNAVAILABLE → quantum redistribute.
- `packages/data/providers/news/{__init__,rss,classify,fixtures}.py`,
  `packages/data/providers/calendar/__init__.py`, `config/event_calendar.yaml`,
  `packages/data/types.py` — önceki session WIP'i (compile-safe doğrulandı;
  ruff RUF100 kullanılmayan noqa temizlendi).
- `tests/unit/test_rotation.py` — yeni.

## Tests run

- `pytest` → **155 passed** (5 yeni).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  (CI scope) → **All checks passed**.
- `apps/web: pnpm tsc --noEmit` → **exit 0** (tip temiz).
- `pnpm build` → **atlandı**: frontend sıfır diff + canlı Clean dev sunucusu
  (3000) aynı `.next`'i kullanıyor, build onu 500'e düşürürdü. tsc gate yeterli.

## Live dashboard smoke

- API (127.0.0.1:8000): `/health` 200; `/data/snapshot` 200 (gerçek
  fiyatlar — SSL cert ile live); `provider_status` rotation/news/geo_news/
  calendar = ok.
- Rotation (regime-report layer "Sermaye Rotasyonu"): gerçek skor + evidence
  (DOLAR_GÜCÜ/HİSSE/ALTIN akışı, 30g momentum %, BTC/GLD·BTC/DXY·GLD/DXY oran
  sinyalleri). Hash-mock kayboldu.
- Web (127.0.0.1:3000): SSR 200, paneller mevcut (Sermaye Rotasyonu /
  capital_rotation / news / PAPER), title "Clean E-yAy".

## PAPER_SAFE check

- broker: none · real order: none · live execution: none
- RiskGate/DQS/KillSwitch/halt: sıfır diff (değişmedi)
- LLM karar motoruna sokulmadı; frontend hesap yapmıyor; page.tsx büyümedi.

## SKIPPED / NEXT

- Asset universe expansion: TLT/HYG/LQD/JNK/IWM/SMH/XLF/FXI provider'a
  eklenmedi → rotation canlıda 6/9 seri ile çalışıyor (BTC/GLD/XAG/DXY/OIL/
  SP500). Engine bu semboller eklenince otomatik kullanır. CoinGecko
  dominance + FRED HY spread/real yield/M2/PPI de bu fazda yok.
- news/geo/calendar birim testleri (RSS fixture parse, geo classification,
  YAML load, high-impact event → WATCH) yazılmadı — sağlayıcılar canlı
  smoke ile doğrulandı, unit coverage NEXT.
- Event risk RiskGate bağı (`packages/risk/event_risk.py` kısıtlayıcı
  WATCH/NO_POSITION_INCREASE) bu fazda bağlanmadı.
