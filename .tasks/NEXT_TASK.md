# NEXT TASK — G6 Confidence Calibration (Platt scaling tam entegrasyon)

`packages/learning/calibration.py` zaten Platt fit/apply içeriyor; bunu
gerçek decision akışına ve dashboard'a tam bağla.

## Scope

- Karar engine her trade için `predicted_confidence` üretir (consensus
  skor → logit → Platt). Bu değer Position/Trade'e kaydedilir.
- Closed trade'lerden `[(predicted, won)]` örnekleri toplanır; periyodik
  `fit_platt` ile (a, b) parametreleri öğrenilir.
- Parametreler dosyaya yazılır: `data/runtime/platt.json`. Kararda
  `apply_platt` ile düzeltilmiş confidence üretilir.
- `/api/v1/learning/calibration` endpoint'i — `bins`, `(a,b)`, sample
  count.
- DATA_POLICY: yalnızca `data_verified=True` trade'ler örneklere alınır.

## Dashboard parallel visibility

- `CalibrationPanel` (varsa LearningPanel içinde) gerçek bin'leri ve (a,b)
  parametrelerini gösterir; eski placeholder (0.5 baseline) kaldırılır.

## Rules

- `PAPER_SAFE / NO_EXECUTION`
- Decision threshold'larını gevşetme.
- Owner approval rule sadece weights için; calibration parametreleri
  workshop verisinden öğrenilir, ayrı bir approval gerektirmez (audit
  trail tutulur).
- Test offline: Trade örnekleri seed edilir.
