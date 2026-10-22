/**
 * Presentation-only speech normalisation.
 *
 * The dashboard keeps its precise symbols/codes on screen. Piper receives a
 * spoken form instead, so tickers, timeframes and gate identifiers cannot be
 * read as arbitrary English words. Every web voice entry point uses this one
 * function (the API applies the same safety normalisation again).
 */
const ENGLISH_TO_TURKISH: Array<[RegExp, string]> = [
  [/Here[’']s what happened in crypto today/gi, "Bugün kripto piyasasında yaşananlar"],
  [/Big Tech/gi, "büyük teknoloji şirketleri"],
  [/may leave/gi, "riske atabilir"],
  [/crypto bots exposed/gi, "kripto botlarını açıkta bırakabilir"],
  [/CertiK warns/gi, "CertiK uyarıyor"],
  [/Gold turns higher as oil prices dip/gi, "Petrol fiyatları düşerken altın yükseliyor"],
  [/investors eye Fed rate outlook/gi, "yatırımcılar Fed'in faiz görünümünü izliyor"],
  [/Breaking News/gi, "son dakika haberi"],
  [/Latest News and Videos/gi, "son haberler ve videolar"],
  [/\bbullish\b/gi, "yukarı yönlü"],
  [/\bbearish\b/gi, "aşağı yönlü"],
  [/\bneutral\b/gi, "nötr"],
  [/\bLONG\b/g, "alış"],
  [/\bSHORT\b/g, "satış"],
  [/\bWATCH\b/gi, "izlemede"],
  [/\bHOLD\b/gi, "beklemede"],
  [/\bNFP\b/g, "tarım dışı istihdam verisi"],
  [/\bCPI\b/g, "enflasyon verisi"],
  [/\bAI\b/g, "yapay zekâ"],
  [/\bETF\b/g, "borsa yatırım fonu"],
  [/\bPnL\b/g, "kâr zarar"],
  [/\bpaper[_ -]?only\b/gi, "yalnızca kâğıt üzerinde"],
  [/\bno[_ -]?execution\b/gi, "gerçek emir yok"],
  [/White House event/gi, "Beyaz Saray etkinliği"],
];

const CODE_TO_SPOKEN: Array<[RegExp, string]> = [
  [/\bXAUUSD\b/gi, "altın"],
  [/\bXAGUSD\b/gi, "gümüş"],
  [/\bBTCUSD\b/gi, "Bitcoin"],
  [/\bETHUSD\b/gi, "Ethereum"],
  [/\bSP500\b/gi, "S ve P beş yüz"],
  [/\bBRENT\b/gi, "Brent petrol"],
  [/\bDXY\b/gi, "dolar endeksi"],
  [/\bVIX\b/gi, "VİKS"],
  [/\bABD\b/g, "Amerika Birleşik Devletleri"],
  [/\bGENIUS Kanunu\b/gi, "yeni kripto yasası"],
  [/\bMACD(?:_histogram_positive)?\b/gi, "MACD göstergesi pozitif"],
  [/\bRSI\b/gi, "R S İ göstergesi"],
  [/\bDQS\b/gi, "veri kalitesi skoru"],
  [/\bR:R\b/gi, "risk getiri oranı"],
  [/\bRR\b/gi, "risk getiri oranı"],
  [/\bconcentration[_ -]?guard\b/gi, "pozisyon yoğunlaşma sınırı"],
  [/\bconfidence[_ -]?floor\b/gi, "güven alt sınırı"],
  [/\bcorrelation[_ -]?veto\b/gi, "korelasyon engeli"],
  [/\bentry[_ -]?quality(?:[_ -]?v2)?\b/gi, "giriş kalitesi"],
  [/\bblocked[_ -]?by\b/gi, "engel"],
  [/\bpaper[_ -]?action\b/gi, "kâğıt işlem"],
  [/\b(\d+)\s*h\b/gi, "$1 saat"],
  [/\b(\d+)\s*m\b/gi, "$1 dakika"],
  [/\b(\d+)\s*d\b/gi, "$1 gün"],
  [/(?:Seeking Alpha|Cointelegraph|CryptoSlate|Gold Wire|World Wire|Investing\.com)/gi, "haber kaynağı"],
  [/\bAP News\b/gi, "haber ajansı"],
];

export function normalizeVoiceText(value: string, maxChars = 3600): string {
  let text = String(value || "").normalize("NFC").replace(/i\u0307/g, "i");
  text = text.replace(/[\u200B-\u200D\uFEFF]/g, "");
  for (const [pattern, replacement] of ENGLISH_TO_TURKISH) text = text.replace(pattern, replacement);
  for (const [pattern, replacement] of CODE_TO_SPOKEN) text = text.replace(pattern, replacement);
  return text
    .replace(/https?:\/\/\S+/gi, "haber bağlantısı")
    .replace(/\|/g, ". ")
    .replace(/→/g, " yönü ")
    .replace(/\$/g, " dolar ")
    .replace(/%/g, " yüzde ")
    .replace(/[\/\\]/g, " ")
    .replace(/[•·◆◇]+/g, ".")
    .replace(/[_*`#<>[\](){}]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxChars);
}
