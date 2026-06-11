# Dashboard Rules — Clean E-yAy

## Paralel büyüme kuralı

- Backend yeni state üretirse, dashboard'da **minimum görünürlük** eklenir
  (en azından bir panelde gösterilir veya mevcut panele alan eklenir).
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
  ruhu korunur — `HeroScene` ve neon cyan/magenta tema değiştirilmez.

## G1 için (gerçek provider)

Yeni paneller / görünürlük:

- `DataQualityPanel`
- `ProviderStatusPanel`
- `SnapshotPanel`
- `MarketDataPanel`

Bunlar için selector + panel-registry girişleri eklenmelidir.
