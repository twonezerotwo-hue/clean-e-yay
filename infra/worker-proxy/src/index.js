// Cockpit E-yAy — Cloudflare Worker reverse proxy.
//
// Amaç: kullanıcı `https://cockpit-eyay.<sub>.workers.dev` adresini görür;
// Worker isteği arkadan UPSTREAM'e (cloudflared trycloudflare URL'si)
// yönlendirir. Yanıt aynı bağlantı üzerinden kullanıcıya döner. Adres
// çubuğunda hiçbir zaman tunnel URL'si görünmez.

export default {
  async fetch(request, env) {
    const upstream = env.UPSTREAM;
    if (!upstream) {
      return new Response("UPSTREAM not configured", { status: 500 });
    }

    const reqUrl = new URL(request.url);
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
