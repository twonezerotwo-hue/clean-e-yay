# Prompt Protocol — Clean E-yAy

Her görev için Claude şu sırayı izler:

1. `docs/AGENT_CONTEXT.md` oku.
2. `docs/SAFETY_RULES.md` oku.
3. `docs/CURRENT_STATE.md` oku.
4. `docs/ROADMAP.md` oku.
5. Frontend dokunuluyorsa `docs/DASHBOARD_RULES.md` oku.
6. `.tasks/NEXT_TASK.md` oku.
7. Sadece `NEXT_TASK.md` içindeki görevi yap.
8. Tüm mimariyi yeniden tartışma.
9. `NEXT_TASK.md` açıkça belirtmedikçe çalışan sistemleri yeniden yazma.
10. Patch'leri küçük tut, mantıklı parçalar halinde commit et.
11. `.tasks/TASK_RESULT.md` güncelle.
12. `docs/CURRENT_STATE.md` güncelle.
13. `.tasks/CHANGELOG_AGENT.md`'ye kısa not ekle.

## Kısa prompt formatı (bundan sonra kullanılacak)

```
Read protocol. Do NEXT_TASK.
```

veya yeni bir görev tanımlamak için:

```
Update .tasks/NEXT_TASK.md with: <görev tanımı>
Then read protocol and do it.
```
