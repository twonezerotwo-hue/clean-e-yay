# Dashboard Rules — Clean E-yAy

## Panel kuralı (owner kararı K8, 2026-10-02)

- Ana ekran **yalnız** owner'ın karar verdiği veya her gün baktığı konuları
  panel olarak gösterir.
- Backend'in ürettiği diğer state'ler kendi panelini almaz; tek bir
  **Detaylar** sayfasında liste/alan olarak görünür. Hiçbir state gizlenmez.
- Eski "backend yeni state üretirse panel eklenir" kuralı kaldırıldı.
- Frontend hesap yapmaz — tüm türetilmiş değerler `lib/selectors/` içinden
  gelir.
- Yeni panel eklenirken `lib/panel-registry.ts` güncellenir (id, title,
  defaultVisible, span, group).
- `app/page.tsx` büyütülmez — yeni panel `GridCell` + registry üzerinden
  eklenir, sayfa düzeni yeniden yazılmaz.
- Her panel `PanelFrame` (ErrorBoundary + telemetry) içinde,
  `DashboardGrid` / `GridCell` ile yerleştirilir.
- Veri kalitesi gösterilen yerlerde `DataQualityBadge` kullanılır.
- 3D / R3F (`@react-three/fiber`, `@react-three/drei`) ve Framer Motion
  ruhu korunur — canlı 3D sahneler (`SpaceBrainScene`, `HoloHeadScene`,
  `QuantumBackplaneScene`) ve neon cyan/magenta tema değiştirilmez.
