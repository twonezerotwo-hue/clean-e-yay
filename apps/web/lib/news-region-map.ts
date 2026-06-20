/**
 * Haber bölgesi → harita koordinatı (equirectangular 1000×500).
 *
 * Görünen etiketler Türkçe. `classifyHeadlineRegion` haber metninden spesifik
 * bölgeyi çıkarır; backend `NewsHeadline.region` kaba etiketi (USA/Europe/…)
 * dönerse onu fallback olarak kullanır.
 *
 * x = (lon + 180) / 360 * 1000,  y = (90 - lat) / 180 * 500
 */

export type GeoPoint = { x: number; y: number; region: string };

const COORDS: Record<string, GeoPoint> = {
  usa:     { x: 286, y: 142, region: "ABD" },
  europe:  { x: 524, y: 111, region: "Avrupa" },
  uk:      { x: 500, y: 107, region: "İngiltere" },
  russia:  { x: 604, y: 95,  region: "Rusya" },
  ukraine: { x: 585, y: 110, region: "Ukrayna" },
  turkey:  { x: 591, y: 139, region: "Türkiye" },
  iran:    { x: 643, y: 151, region: "İran" },
  israel:  { x: 598, y: 162, region: "İsrail" },
  lebanon: { x: 599, y: 156, region: "Lübnan" },
  saudi:   { x: 630, y: 181, region: "Suudi Arabistan" },
  china:   { x: 823, y: 139, region: "Çin" },
  japan:   { x: 888, y: 151, region: "Japonya" },
  india:   { x: 714, y: 171, region: "Hindistan" },
  global:  { x: 389, y: 167, region: "Küresel" },
};

const COARSE: Record<string, string> = {
  USA: "usa",
  Europe: "europe",
  Russia: "russia",
  China: "china",
  Iran: "iran",
  Israel: "israel",
  Turkey: "turkey",
  "Middle East": "saudi",
  Global: "global",
};

// Pattern öncelik sıralı — özel lokasyon kaba ülke adından önce.
const PATTERNS: Array<[RegExp, string]> = [
  [/lebanon|beirut|hezbollah/i,                              "lebanon"],
  [/israel|tel aviv|jerusalem|\bidf\b|netanyahu|gaza/i,      "israel"],
  [/iran|tehran|hormuz|persian gulf/i,                       "iran"],
  [/ukraine|kyiv|kiev|kharkiv|odesa|donbas|zelensk|crimea/i, "ukraine"],
  [/russia|moscow|kremlin|putin/i,                           "russia"],
  [/china|beijing|shanghai|xi jinping|\bpboc\b|taiwan/i,     "china"],
  [/japan|tokyo|\bboj\b|\byen\b/i,                           "japan"],
  [/india|delhi|mumbai|\brbi\b/i,                            "india"],
  [/turkey|türkiye|ankara|istanbul|erdogan|erdoğan/i,        "turkey"],
  [/saudi|riyadh|opec|aramco/i,                              "saudi"],
  [/\buk\b|britain|london|\bboe\b|sterling/i,                "uk"],
  [/europe|\becb\b|germany|france|berlin|paris|brussels|eurozone/i, "europe"],
  [/trump|white house|pentagon|washington|congress|\bfed\b|fomc|treasury|nato|newark|laguardia|\bus\b|u\.s\./i, "usa"],
];

/**
 * Haber metninden (varsa backend'in kaba region etiketinden) spesifik bölge
 * anahtarını çıkarır. Anahtar `COORDS` map'inin key'idir.
 */
export function classifyHeadlineRegion(text: string, backendRegion?: string | null): string {
  if (text) {
    for (const [re, key] of PATTERNS) {
      if (re.test(text)) return key;
    }
  }
  if (backendRegion && COARSE[backendRegion]) return COARSE[backendRegion];
  return "global";
}

export function geoForRegion(key: string | null | undefined): GeoPoint {
  if (!key) return COORDS.global;
  if (key in COORDS) return COORDS[key];
  // Eski kaba etiket geldiğinde fallback.
  if (COARSE[key]) return COORDS[COARSE[key]];
  return COORDS.global;
}
