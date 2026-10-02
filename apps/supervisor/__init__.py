"""Supervisor — API + tick_worker + learning_worker tek süreçte.

apps/api ince HTTP katmanı kalır (arka plan döngüsü içermez — architecture
guard). Lokal keeper ve AWS bu süreci çalıştırır (owner kararı K6):

    python -m apps.supervisor

Event loop yalnız HTTP'ye kalır; tick ve learning ayrı thread'de koşar.
"""
