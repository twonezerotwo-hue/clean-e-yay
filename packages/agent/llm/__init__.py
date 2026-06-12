"""v2.6 — LLM persona katmanı (narrative-only).

LLM karar VERMEZ: bu paket yalnızca mevcut backend state'ini açıklayan,
eleştiren ve özetleyen anlatı katmanıdır. Hiçbir çıktı decision/risk/paper
akışına geri yazılmaz (SAFETY_RULES + ARCHITECTURE §2).

- `client`  — LLM_MODE=off|mock|groq; Groq adapter (anahtar yoksa network
  çağrısı YAPMADAN None döner, sistem deterministik fallback ile sürer).
- `budget`  — per-request max token + günlük token bütçesi (file-backed).
- `cache`   — 2 saatlik file-backed yanıt cache'i.
- `context` — persona/chat prompt'larına giren KOMPAKT state özeti
  (full raw market data asla prompt'a gömülmez).
- `guard`   — prompt injection / bypass taleplerine güvenli ret.
- `report`  — persona bölümleri (LLM veya deterministik fallback).
- `chat`    — state-grounded soru-cevap.
"""
