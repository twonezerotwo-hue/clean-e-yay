import type { NewsHeadline } from "@/types/generated/api";

type LinkKind = "direct" | "source_search";

export type NewsLink = {
  href: string;
  host: string;
  kind: LinkKind;
  label: string;
  title: string;
};

type SourceTarget = {
  host: string;
  label: string;
  re: RegExp;
  search: (query: string) => string;
};

const SOURCE_TARGETS: SourceTarget[] = [
  {
    host: "apnews.com",
    label: "AP News",
    re: /\bap news\b|\bassociated press\b/i,
    search: (q) => `https://apnews.com/search?q=${encodeURIComponent(q)}`,
  },
  {
    host: "cnbc.com",
    label: "CNBC",
    re: /\bcnbc\b/i,
    search: (q) => `https://www.cnbc.com/search/?query=${encodeURIComponent(q)}`,
  },
  {
    host: "coindesk.com",
    label: "CoinDesk",
    re: /\bcoindesk\b/i,
    search: (q) => `https://www.coindesk.com/search?s=${encodeURIComponent(q)}`,
  },
  {
    host: "cointelegraph.com",
    label: "Cointelegraph",
    re: /\bcointelegraph\b/i,
    search: (q) => `https://cointelegraph.com/search?query=${encodeURIComponent(q)}`,
  },
  {
    host: "investing.com",
    label: "Investing.com",
    re: /\binvesting\b/i,
    search: (q) => `https://www.investing.com/search/?q=${encodeURIComponent(q)}`,
  },
  {
    host: "bloomberg.com",
    label: "Bloomberg",
    re: /\bbloomberg\b/i,
    search: (q) => `https://www.bloomberg.com/search?query=${encodeURIComponent(q)}`,
  },
  {
    host: "ft.com",
    label: "Financial Times",
    re: /\bfinancial times\b|\bft\b/i,
    search: (q) => `https://www.ft.com/search?q=${encodeURIComponent(q)}`,
  },
  {
    host: "decrypt.co",
    label: "Decrypt",
    re: /\bdecrypt\b/i,
    search: (q) => `https://decrypt.co/search?q=${encodeURIComponent(q)}`,
  },
  {
    host: "reuters.com",
    label: "Reuters",
    re: /\breuters\b/i,
    search: (q) => `https://www.reuters.com/site-search/?query=${encodeURIComponent(q)}`,
  },
];

const DIRECT_URL_FIELDS = [
  "url",
  "link",
  "source_url",
  "canonical_url",
  "article_url",
  "external_url",
  "permalink",
] as const;

type RawHeadline = NewsHeadline & Partial<Record<(typeof DIRECT_URL_FIELDS)[number], unknown>>;

function cleanSearchTitle(title: string) {
  return title
    .replace(/\s[-–—]\s(?:AP News|Bloomberg\.com|Reuters|CNBC|CoinDesk|Decrypt)\s*$/i, "")
    .replace(/\s\|\s(?:Reuters|CNBC|CoinDesk|Decrypt)\s*$/i, "")
    .trim();
}

function directUrl(h: NewsHeadline) {
  const raw = h as RawHeadline;
  for (const field of DIRECT_URL_FIELDS) {
    const value = raw[field];
    if (typeof value === "string" && /^https?:\/\//i.test(value)) {
      return value;
    }
  }
  return null;
}

function hostname(href: string) {
  try {
    return new URL(href).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function targetForHeadline(h: NewsHeadline) {
  const text = `${h.source} ${h.title} ${h.title_tr ?? ""}`;
  return SOURCE_TARGETS.find((target) => target.re.test(text)) ?? null;
}

export function resolveNewsLink(h: NewsHeadline): NewsLink {
  const direct = directUrl(h);
  if (direct) {
    const host = hostname(direct);
    return {
      href: direct,
      host,
      kind: "direct",
      label: host || "Kaynak",
      title: "Haberi kendi kaynağında aç",
    };
  }

  const target = targetForHeadline(h);
  const query = cleanSearchTitle(h.title_tr?.trim() || h.title);
  if (target) {
    return {
      href: target.search(query),
      host: target.host,
      kind: "source_search",
      label: target.label,
      title: `${target.label} içinde bu başlığı ara`,
    };
  }

  return {
    href: "#",
    host: "",
    kind: "source_search",
    label: "Kaynak yok",
    title: "Backend bu haber için kaynak URL döndürmüyor",
  };
}
