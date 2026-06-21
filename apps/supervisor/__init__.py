"""Supervisor — API + tick_worker + learning_worker tek event-loop'ta.

apps/api ince HTTP katmanı kalır (arka plan döngüsü içermez — architecture
guard). Bu supervisor, üç süreci tek komutla birlikte çalıştırmak içindir:

    python -m apps.supervisor

Her şeyi tek process'te asyncio task olarak yönetir (Windows'ta tek pencere,
ücretsiz 7/24). Worker'ları ayrı process olarak istersen `make workers` veya
docker-compose hâlâ geçerli.
"""
