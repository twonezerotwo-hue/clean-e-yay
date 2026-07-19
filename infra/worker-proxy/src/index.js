// Cockpit E-yAy — Cloudflare Worker reverse proxy.
//
// Amaç: kullanıcı `https://cockpit-eyay.<sub>.workers.dev` adresini görür;
// Worker isteği arkadan UPSTREAM'e (cloudflared trycloudflare URL'si)
// yönlendirir. Yanıt aynı bağlantı üzerinden kullanıcıya döner. Adres
// çubuğunda hiçbir zaman tunnel URL'si görünmez.
//
// T2 (2026-07 dış denetim P0-4) — parola kapısı:
//   * `ACCESS_PASSWORD` secret'ı TANIMLIYSA: tarayıcı ilk girişte parola sorar
//     (HttpOnly çerez, 30 gün). Çerezsiz /api/* istekleri 401 alır.
//   * `API_AUTH_TOKEN` secret'ı TANIMLIYSA: parola kapısından geçen isteklere
//     Worker `Authorization: Bearer <token>` başlığını EKLER — token tarayıcıya
//     hiç inmez; API tarafı da aynı token'ı yazma isteklerinde şart koşar.
//   * İkisi de tanımsızsa davranış birebir eski pass-through (bayt-aynı).
// Kurulum: `wrangler secret put ACCESS_PASSWORD` + `wrangler secret put
// API_AUTH_TOKEN` (değerler git'e YAZILMAZ).

const AUTH_COOKIE = "eyay_auth";

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEq(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.byteLength !== bb.byteLength) return false;
  // Cloudflare Workers runtime'ında mevcut (non-standard); yoksa düz kıyas.
  return crypto.subtle.timingSafeEqual
    ? crypto.subtle.timingSafeEqual(ab, bb)
    : a === b;
}

function getCookie(request, name) {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=");
  }
  return null;
}

function loginPage(showError) {
  const err = showError
    ? '<p style="color:#e07168;margin:0 0 12px">Parola yanlış — tekrar dene.</p>'
    : "";
  const html = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>E-yAy Kokpit — Giriş</title></head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0e1319;color:#e3e9ef;font-family:-apple-system,Segoe UI,Roboto,sans-serif">
<form method="post" action="/__login" style="background:#161d26;padding:32px 36px;border-radius:10px;border:1px solid #2a333d;min-width:260px">
<h1 style="font-size:18px;margin:0 0 16px">E-yAy Kokpit</h1>${err}
<input type="password" name="password" placeholder="Parola" autofocus required
 style="width:100%;box-sizing:border-box;padding:10px;border-radius:6px;border:1px solid #2a333d;background:#0e1319;color:#e3e9ef;margin-bottom:12px">
<button type="submit" style="width:100%;padding:10px;border-radius:6px;border:0;background:#175e63;color:#fff;font-weight:600;cursor:pointer">Giriş</button>
</form></body></html>`;
  return new Response(html, {
    status: showError ? 401 : 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    const upstream = env.UPSTREAM;
    if (!upstream) {
      return new Response("UPSTREAM not configured", { status: 500 });
    }

    const reqUrl = new URL(request.url);

    // ── T2 parola kapısı (ACCESS_PASSWORD tanımlıysa) ─────────────────────
    let gateAuthed = false;
    if (env.ACCESS_PASSWORD) {
      // Çerez, ham parola değil türetilmiş imza taşır; parola değişince
      // tüm eski çerezler kendiliğinden geçersizleşir.
      const expected = await sha256Hex(`${env.ACCESS_PASSWORD}|eyay-cookie-v1`);

      if (reqUrl.pathname === "/__login" && request.method === "POST") {
        const form = await request.formData().catch(() => null);
        const attemptHash = await sha256Hex(
          `${form?.get("password") ?? ""}|eyay-cookie-v1`,
        );
        if (timingSafeEq(attemptHash, expected)) {
          return new Response(null, {
            status: 303,
            headers: {
              location: "/",
              "set-cookie":
                `${AUTH_COOKIE}=${expected}; HttpOnly; Secure; Path=/; ` +
                "SameSite=Lax; Max-Age=2592000",
            },
          });
        }
        return loginPage(true);
      }

      gateAuthed = timingSafeEq(getCookie(request, AUTH_COOKIE) || "", expected);
      if (!gateAuthed) {
        if (reqUrl.pathname.startsWith("/api/")) {
          return new Response(JSON.stringify({ detail: "unauthorized" }), {
            status: 401,
            headers: { "content-type": "application/json" },
          });
        }
        return loginPage(false);
      }
    }

    const targetUrl = new URL(upstream);
    targetUrl.pathname = reqUrl.pathname;
    targetUrl.search = reqUrl.search;

    // Yeni Request: aynı method/body/headers, sadece host upstream'e döner.
    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set("host", targetUrl.host);
    upstreamHeaders.delete("cf-connecting-ip");
    upstreamHeaders.delete("cf-ipcountry");
    upstreamHeaders.delete("cf-ray");
    upstreamHeaders.delete("cf-visitor");
    // T2 — API token'ı YALNIZ parola kapısından geçmiş isteğe eklenir;
    // tarayıcıya hiç inmez, dışarıdan gelen sahte Authorization ezilir.
    if (env.API_AUTH_TOKEN && gateAuthed) {
      upstreamHeaders.set("authorization", `Bearer ${env.API_AUTH_TOKEN}`);
    }

    const upstreamReq = new Request(targetUrl.toString(), {
      method: request.method,
      headers: upstreamHeaders,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : request.body,
      redirect: "manual",
    });

    const upstreamRes = await fetch(upstreamReq);

    // SSE (text/event-stream): TransformStream ile body'i pipe et — bu
    // Cloudflare'in chunk'ları biriktirmesini engeller. ÖNEMLI KISIT:
    // cloudflared 'quick' tunnel (trycloudflare.com) tarafı bir başka
    // buffering katmanı ekliyor; named tunnel veya doğrudan Worker→origin
    // bağlantısı olmadan SSE üzerinden tunnel'a sub-saniye latency
    // garanti edilemez. Bu durumda web tarafı polling fallback'iyle
    // (react-query refetchInterval) çalışır.
    const ct = upstreamRes.headers.get("content-type") || "";
    if (ct.startsWith("text/event-stream")) {
      const { readable, writable } = new TransformStream();
      upstreamRes.body.pipeTo(writable).catch(() => {});
      const sseHeaders = new Headers(upstreamRes.headers);
      sseHeaders.set("cache-control", "no-cache, no-transform");
      sseHeaders.set("x-accel-buffering", "no");
      sseHeaders.delete("content-encoding");
      return new Response(readable, {
        status: upstreamRes.status,
        statusText: upstreamRes.statusText,
        headers: sseHeaders,
      });
    }

    // Diğer yanıtlar için header'ı normalleştirmek üzere sarma OK.
    const resHeaders = new Headers(upstreamRes.headers);
    return new Response(upstreamRes.body, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: resHeaders,
    });
  },
};
