/**
 * Yazma anahtarı (owner kararı 2a, 2026-10-03).
 *
 * API_AUTH_TOKEN tanımlıyken API tüm yazma isteklerini (POST/PUT/PATCH/DELETE —
 * sohbet ve ses dahil) `Authorization: Bearer <token>` ister. Panel anahtarı bir
 * kez sorar, bu tarayıcıda saklar ve yazma isteklerine ekler. Okuma (GET)
 * etkilenmez. AWS'teki Cloudflare Worker kendi anahtarını ekler (bu başlığı ezer),
 * orada soru hiç çıkmaz.
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

/**
 * 401 sonrası: anahtarı sor ve sakla. `true` → çağıran isteği bir kez tekrarlar.
 * Aynı anda düşen birkaç 401 için (sohbet + ses) yalnız bir kez sorulur.
 */
export function requestWriteToken(): boolean {
  if (typeof window === "undefined") return false;
  if (Date.now() - lastSetAt < 5_000 && readToken()) return true;
  // Az önce vazgeçildiyse aynı eylemin diğer istekleri (yedek sohbet, ses) yeniden sormaz.
  if (Date.now() - declinedAt < 10_000) return false;
  const value = window.prompt(
    "Yazma anahtarı gerekli (sohbet, ses ve işlem butonları için).\n" +
      "Bu bilgisayarda C:\\dev\\clean-e-yay\\.env dosyasındaki API_AUTH_TOKEN değerini yapıştır.\n" +
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
}
