/**
 * Yazma anahtarı (owner kararı 2a, 2026-10-03).
 *
 * API_AUTH_TOKEN tanımlıyken API tüm yazma isteklerini (POST/PUT/PATCH/DELETE —
 * sohbet ve ses dahil) `Authorization: Bearer <token>` ister. Panel anahtarı bu
 * tarayıcıda saklar ve yazma isteklerine ekler. Ana bilgisayarda anahtar panelin
 * kendi sunucusundan sessizce alınır (`app/api/local-auth`); telefonda/ngrok'ta
 * yalnız kullanıcı eyleminde bir kez sorulur. Okuma (GET) etkilenmez. AWS'teki
 * Cloudflare Worker kendi anahtarını ekler (bu başlığı ezer), orada soru çıkmaz.
 */

const STORAGE_KEY = "eyay.write_token";
const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let lastSetAt = 0;
let declinedAt = 0;

export function isMutating(method?: string): boolean {
  return MUTATING.has((method ?? "GET").toUpperCase());
}

function readToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeToken(value: string | null): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Depolama kapalıysa (gizli pencere vb.) anahtar yalnız bu oturumda sorulur.
  }
}

/** Yazma isteğiyse kayıtlı anahtarı başlığa ekler. */
export function applyWriteAuth(headers: Headers, method?: string): void {
  if (typeof window === "undefined" || !isMutating(method)) return;
  const token = readToken();
  if (token) headers.set("authorization", `Bearer ${token}`);
}

let localFailedAt = 0;

/** Bu bilgisayardaki panel: anahtarı panelin kendi sunucusundan sessizce al.
 *  Yalnız başarısız deneme 30 sn hatırlanır (telefonda her 401'de boşuna sorgu olmasın). */
async function fetchLocalToken(): Promise<string | null> {
  if (Date.now() - localFailedAt < 30_000) return null;
  try {
    const res = await fetch("/api/local-auth", { cache: "no-store" });
    const body = res.ok ? ((await res.json()) as { token?: unknown }) : {};
    if (typeof body.token === "string" && body.token) return body.token;
  } catch {
    // ağ hatası: başarısız say
  }
  localFailedAt = Date.now();
  return null;
}

/**
 * 401 sonrası anahtar edinme. `true` → çağıran isteği bir kez tekrarlar.
 * 1) Bu bilgisayardaysa sunucudan sessizce alınır (soru yok).
 * 2) Değilse (telefon/ngrok) yalnız kullanıcı eyleminde (`interactive`) bir kez
 *    sorulur; sesli okuma gibi arka plan istekleri asla soru açmaz.
 */
export async function requestWriteToken(interactive: boolean): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (Date.now() - lastSetAt < 5_000 && readToken()) return true;
  const local = await fetchLocalToken();
  if (local) {
    writeToken(local);
    lastSetAt = Date.now();
    return true;
  }
  if (!interactive) return false;
  // Az önce vazgeçildiyse aynı eylemin diğer istekleri (yedek sohbet) yeniden sormaz.
  if (Date.now() - declinedAt < 10_000) return false;
  const value = window.prompt(
    "Yazma anahtarı gerekli (sohbet, ses ve işlem butonları için).\n" +
      "Ana bilgisayardaki C:\\dev\\clean-e-yay\\.env dosyasındaki API_AUTH_TOKEN değerini yapıştır.\n" +
      "Bu tarayıcıda saklanır; bir kez sorulur.",
  );
  if (!value || !value.trim()) {
    declinedAt = Date.now();
    return false;
  }
  writeToken(value.trim());
  lastSetAt = Date.now();
  return true;
}

/** Tekrar denemede de 401 → anahtar yanlış: sil, bir sonraki istekte yeniden sorulsun. */
export function rejectWriteToken(): void {
  writeToken(null);
  lastSetAt = 0;
  localFailedAt = 0; // anahtar değişmiş olabilir: yerel sunucudan bir kez daha denensin
}
