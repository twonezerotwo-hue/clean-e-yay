# NEXT TASK — seç (UX2 sonrası)

**UX2 — Dashboard Polish** tamamlandı (bkz. `.tasks/TASK_RESULT.md` +
`docs/CURRENT_STATE.md`): uzman bölümü 6 başlığa gruplandı, vague "veya" copy
temizlendi (tek main_blocker), AgentBrief stance callout, chat "Agent'a Sor" +
intent'e net öneri, responsive matris. Frontend-only; backend SIFIR diff.
tsc/build temiz, canlı SSR smoke 8/8 PASS. Commit:
`feat(web): polish agent cockpit usability`.

A1 (RC audit) + DEP1 (deploy) + UX2 (polish) bitti. **Backend FREEZE** — yalnızca
P0 hotfix. Aşağıdaki üç yönden biri seçilir:

## Seçenek A — Release packaging / local production run checklist (önerilen)
Backend RC + deploy checklist + cockpit hazır; doğal sıradaki adım gerçek bir
"sürüm paketi": versiyon/tag, CHANGELOG → release notes, tek-komut prod run
doğrulaması (api+tick+web ayağa, learning scheduled, smoke yeşil), launchd/systemd/
compose örnek dosyaları, `data/runtime` volume + yedek notu. Kod gerekiyorsa minimal
(çoğu docs/ops). Backend FREEZE korunur.

## Seçenek B — UX3 live user feedback polish
Gerçek kullanıcı oturumuyla cockpit'i izle: ilk-bakış anlaşılırlığı, panel
yoğunluğu, kopya netliği, mobil/tablet, dark-neon kontrast. Frontend-only;
backend SIFIR diff. Panel görünürlük tercih kalıcılığı (localStorage) bu turda
tamamlanabilir.

## Seçenek C — only P0 backend hotfix mode
Yeni iş açma; backend'i dondurulmuş RC olarak bırak, yalnızca gerçek P0 bug
çıkarsa minimal + testli hotfix. Opsiyonel: A1 P1 hardening (H1–H5) — 5 düşük-churn
store atomik write, schema_version, ARCHITECTURE.md çok-agent şemasını "vizyon"
işaretle, gerçek openapi-typescript codegen, `decide_all` test-only notu.

## Hard rules (her seçenekte)
- Backend FREEZE: packages/ + apps/api + worker SIFIR diff (P0 hotfix hariç).
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt dokunulmaz.
- Yeni data source / dashboard redesign / intelligence / trading logic YOK.
- Frontend hesap yapmaz; openapi/TS şeması değişmez (codegen drift yeşil kalır).

## Validation (değişen katmana göre)
- Frontend: `cd apps/web && pnpm tsc --noEmit && pnpm build` + `make smoke`.
- Backend dokunulursa (yalnızca P0): `pytest -q` (izole runtime path env'leri) +
  `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
  + codegen/contract drift.
