import { NextResponse, type NextRequest } from "next/server";

// Her istekte çalışır (statik üretilmez); env çalışma anında okunur.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const LOCAL_HOSTS = new Set(["localhost:4000", "127.0.0.1:4000"]);
const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

const notAvailable = () =>
  NextResponse.json({ detail: "not available" }, { status: 404, headers: { "cache-control": "no-store" } });

/**
 * Yalnız BU bilgisayardaki panel için yazma anahtarı (API_AUTH_TOKEN).
 *
 * Lokal keeper web'i `WEB_LOCAL_WRITE_AUTH=1` ile başlatır; AWS'te bu yoktur → 404.
 * Verilmez: ngrok/uzak istek (Host ngrok alan adı ya da X-Forwarded-For loopback
 * değil), başka bir siteden gelen istek (Sec-Fetch-Site ≠ same-origin; DNS
 * rebinding'de Host da tutmaz). Telefonda anahtar bir eylemde bir kez sorulur.
 */
export function GET(request: NextRequest) {
  const token = process.env.API_AUTH_TOKEN?.trim();
  const host = (request.headers.get("host") ?? "").toLowerCase();
  const site = request.headers.get("sec-fetch-site");
  const forwarded = (request.headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((ip) => ip.trim())
    .filter(Boolean);
  if (
    process.env.WEB_LOCAL_WRITE_AUTH !== "1" ||
    !token ||
    !LOCAL_HOSTS.has(host) ||
    site !== "same-origin" ||
    forwarded.some((ip) => !LOOPBACK.has(ip))
  ) {
    return notAvailable();
  }
  return NextResponse.json({ token }, { headers: { "cache-control": "no-store" } });
}
