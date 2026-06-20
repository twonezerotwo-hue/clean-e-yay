/**
 * Low-poly kıta silüetleri — equirectangular 1000×500 SVG path string'leri.
 * Gerçek kıyı çizgisi değil; radar görseli için yeterli soyutlama.
 * Hiçbir runtime fetch yok; tamamen static.
 */
export const WORLD_LAND_PATHS: string[] = [
  // North America
  "M 90 80 L 230 75 L 285 130 L 290 200 L 240 230 L 175 215 L 130 195 L 95 165 L 80 120 Z",
  // Central America bridge
  "M 215 215 L 250 220 L 260 245 L 235 255 L 220 240 Z",
  // South America
  "M 245 250 L 315 245 L 335 305 L 320 365 L 290 420 L 260 425 L 245 380 L 240 320 Z",
  // Greenland
  "M 360 55 L 415 50 L 425 90 L 395 115 L 360 100 Z",
  // Europe
  "M 460 75 L 575 70 L 580 130 L 555 160 L 495 165 L 470 140 L 460 105 Z",
  // Africa
  "M 480 165 L 580 160 L 605 220 L 595 295 L 555 360 L 510 365 L 475 305 L 465 240 Z",
  // Middle East
  "M 580 155 L 660 150 L 670 195 L 635 215 L 595 205 Z",
  // Asia
  "M 575 65 L 880 70 L 895 145 L 855 215 L 780 245 L 705 240 L 645 215 L 605 175 L 580 130 Z",
  // India peninsula
  "M 700 195 L 745 195 L 750 245 L 715 265 L 695 230 Z",
  // SE Asia + Indonesia
  "M 800 240 L 880 250 L 890 285 L 830 295 L 800 275 Z",
  // Australia
  "M 800 320 L 895 315 L 905 375 L 830 385 L 795 360 Z",
];
