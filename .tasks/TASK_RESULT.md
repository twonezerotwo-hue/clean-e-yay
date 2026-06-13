# TASK RESULT

Date: 2026-06-13
Task: UX3 — Dashboard Information Architecture
Status: completed (frontend-only IA/layout; backend FREEZE korundu — packages/ + apps/* sıfır diff)

## UX3 INFORMATION ARCHITECTURE SUMMARY (ne değişti?)

Dashboard "veri çöplüğü"nden **önem sırasına göre gruplu IA**'ya geçti. İlk ekran
artık tek soruyu cevaplıyor — "agent ne durumda, işlem açıyor mu, açamıyorsa ana
sebep ne". Düz 30-panel grid kalktı; hem simple hem expert **başlıklı gruplara**
ayrıldı (ortak `PanelGroup` helper). `panel-registry.ts` IA grupları gerçek
mimariye göre yeniden tanımlandı (group/tier metadata; layout page.tsx'te elle).
Frontend hesap yapmaz; mevcut selector/brief korundu.

## PANEL GROUPING

- **Simple (ilk ekran, önem sırası):**
  - *Agent Command Center*: AgentBrief (hero, HeroScene üstünde) → Komuta Merkezi
    (Karar Merkezi + AI Analist compact).
  - *Risk & Yürütme Donması*: Risk Kapısı + Drawdown Guard + Paper Action +
    Pozisyon Kontrolleri (KILL_SWITCH/HALT varsa matristen ÖNCE).
  - *Karar İzi / Aday Matrisi*: Timeframe Matrisi + Decision Trace + Agent Kanıt
    Zinciri + Aday Sinyalleri (global gate tek banner — UX1 zaten temiz).
  - *İzlenecek Koşullar*: Watch Conditions.
  - *Agent'a Sor*: Chat.
- **Data Quality & Providers**: Veri Kalitesi · Sağlayıcı Durumu · Snapshot ·
  Piyasa Verisi · Pano Denetimi.
- **Market Structure**: Kripto Türevleri · Volatilite · Options IV/Skew ·
  Korelasyon · Grafik Desenleri · Sermaye Rotasyonu.
- **Macro / Catalyst**: Catalyst Etkisi (önce) · Olay Takvimi · Haberler (ham,
  geri planda) · Senaryo.
- **Paper & Learning**: Paper Trading · Öğrenme · Ağırlık Önerisi · Ağırlık
  Geçmişi · Calibration · Mistake Memory.
- **Ops / System**: Replay Durumu · Sistem Sağlığı · Sözleşme/codegen notu.

## Diğer iyileştirmeler (task #4–#8)
- **#4 copy**: AIReportPanel (UX2'de) + DecisionPanel zaten tek `main_blocker`
  kullanıyor (DQS OK + KILL_SWITCH → ana sebep KILL_SWITCH; backend cockpit
  öncelik sırası). Yeni belirsiz "X veya Y" copy yok.
- **#5 replay**: ReplayStatusPanel zaten dürüst (R1/R2) — active_snapshot_replay /
  insufficient mode rozeti + "NO LIVE EXECUTION"; stale "REZERVE" copy yok. Ana
  ekrandan çıkıp **Ops / System** altına alındı.
- **#6 learning**: ana ekrandan **Paper & Learning** expert grubuna alındı; yetersiz
  örnekte tek satır: "Learning inactive — insufficient verified closed trades (n/min)".
- **#7 news**: ham Haberler **Macro / Catalyst** altında, **Catalyst Etkisi önce**.
- **#8 system/provider**: ProviderStatus/MarketData/Snapshot/PanelAudit ana ekrandan
  çıktı → Data Quality & Providers grubu.
- **#9 responsive**: TimeframeMatrix overflow-x-auto (UX2) korundu; grup gridleri
  `grid-cols-1 lg:grid-cols-3` (mobil/tablet tek sütun — taşma yok); başlıklar wrap.

## FILES CHANGED

- `apps/web/app/page.tsx` — simple 5 bölüm + expert 5 grup (`PanelGroup` helper;
  eski `ExpertGroup` yeniden adlandırıldı). Hero = Agent Command Center. Footer
  PAPER_ONLY hatırlatması.
- `apps/web/lib/panel-registry.ts` — yeni `PanelGroupId` (command/risk/decision/
  watch/chat + data/market/macro/learning/ops); her panel doğru gruba; IA sırası.
- `apps/web/components/panels/LearningPanel/index.tsx` — insufficient tek-satır copy.
- docs/CURRENT_STATE.md · .tasks/{TASK_RESULT,CHANGELOG_AGENT,NEXT_TASK}.md

## VALIDATION

- **tsc**: `tsc --noEmit` temiz.
- **build**: `next build` ✓ (`/` static prerender).
- **SSR smoke**: prerendered + live (izole 3061) → HTTP **200**; AgentBrief görünür;
  expert `<details>` **collapsed** (open attr yok); 5 grup başlığı görünür
  (Data Quality & Providers · Market Structure · Macro / Catalyst · Paper & Learning ·
  Ops / System); PAPER_ONLY görünür; HeroScene `<canvas>` korundu; sıralama doğru
  (Agent Brief → Risk & Yürütme → Karar İzi).
- Backend testleri çalıştırılmadı (gerekmez — backend dosyası değişmedi).

## BACKEND FREEZE CHECK

- backend files changed: **no** (yalnızca apps/web/{app,lib,components} + docs).
- trading logic changed: **no**.
- RiskGate changed: **no** (DQS/KillSwitch/halt/paper/learning/replay sıfır diff;
  openapi/TS şeması değişmedi → codegen drift otomatik yeşil).
- PAPER_SAFE intact: **yes** (PAPER_ONLY/NO_EXECUTION rozetleri + footer korundu).

## NEXT

- Öneri: **UX4 live feedback polish** VEYA **production dry-run / soak test** VEYA
  **P0 hotfix only mode**. `.tasks/NEXT_TASK.md` güncellendi.

## COMMITS

- `feat(web): reorganize dashboard information architecture`
