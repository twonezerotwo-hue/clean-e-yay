# API layer

Tüm tipler ve client `contracts/openapi.yaml`'dan üretilir.

```bash
pnpm codegen
```

Bu komut `types/generated/schema.ts` dosyasını yeniler (izlenen üretilmiş dosya
oradadır; eski `lib/api/schema.ts` yolu yanlıştı — kullanılmayan kopya üretiyordu).
Manuel olarak düzenleme.
