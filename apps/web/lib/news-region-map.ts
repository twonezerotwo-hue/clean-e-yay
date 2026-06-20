/**
 * Bölge → harita koordinatı (equirectangular 1000×500).
 *
 * Backend `NewsHeadline.region` zaten classify edilmiş bölge etiketini verir
 * (USA / Iran / Israel / China / Russia / Europe / Middle East). Bu lib
 * yalnızca radar görselinde dot'un nereye çizileceğini söyler — yeni
 * sınıflandırma yapmaz.
 *
 * x = (lon + 180) / 360 * 1000,  y = (90 - lat) / 180 * 500
 */
export type GeoPoint = { x: number; y: number; region: string };

const COORDS: Record<string, GeoPoint> = {
  USA:           { x: 236, y: 142, region: "USA" },
  Iran:          { x: 648, y: 161, region: "Iran" },
  Israel:        { x: 597, y: 164, region: "Israel" },
  China:         { x: 789, y: 153, region: "China" },
  Russia:        { x: 603, y: 81,  region: "Russia" },
  Europe:        { x: 528, y: 111, region: "Europe" },
  "Middle East": { x: 625, y: 175, region: "Middle East" },
};

const GLOBAL: GeoPoint = { x: 500, y: 250, region: "Global" };

export function geoForRegion(region: string | null | undefined): GeoPoint {
  if (!region) return GLOBAL;
  return COORDS[region] ?? GLOBAL;
}
