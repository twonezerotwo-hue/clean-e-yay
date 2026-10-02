# AGENTS.md — Codex ve diğer ajanlar için

Bu repo için tek kural seti `CLAUDE.md` içindedir; önce onu oku. Ajan fark etmeksizin
aynı kurallar geçerlidir. Kısa özet (çelişki olursa CLAUDE.md kazanır):

1. **Paper-safe yapısaldır.** Broker, gerçek emir, `place_order`/`submit_order`/`ccxt` yok.
   `/system/health` daima `paper_safe=true`, `no_execution=true`.
2. **RiskGate finaldir.** Kapılar yalnız kısıtlar; gevşetmek kural ihlalidir.
3. **Gölge-önce.** Yeni davranış flag'i default KAPALI gelir; açmak owner kararıdır.
   Bir PR flag'i kendiliğinden `true` yapmaz.
4. **Golden replay.** `python -m tests.golden.golden_replay --check` bayt-aynı kalmalı.
   Bilinçli davranış değişikliğinde fark PR açıklamasına yazılır, sonra `--write`.
5. **Sözleşme-önce.** Yeni route önce `contracts/openapi.yaml`'a + `make codegen`.
6. **main'e doğrudan push yok.** main = otomatik AWS deploy. Her iş branch + PR + yeşil CI.
7. **Git kimliği.** Commit'ler gerçek owner kimliğiyle atılır (`git config user.name/email`
   ayarlı olmalı; `ADIN <MAIL@ADRESIN.com>` gibi yer tutucu kimlikle commit atma).

Durum: `docs/STATE.md`. Sıradaki iş: `docs/ROADMAP.md`.
