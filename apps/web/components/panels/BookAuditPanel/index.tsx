"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useBookAudit } from "@/lib/queries/hooks";
import type { BookAuditLesson, BookAuditView } from "@/types/generated/api";

// Açık kitap yapısal denetimi (packages/learning/book_audit.py). Canlı açık
// pozisyonları tarar; KAPANIŞ BEKLEMEDEN yapısal mantık hatalarını (aynı sembolde
// zıt yön, tek varlıkta yoğunlaşma, aynı sinyalin TF'lere kopyalanması, korelasyon
// kümesi, tek-yön kitap) kullanıcı diliyle gösterir. Frontend hesap YAPMAZ — tüm
// dersler /api/v1/learning/book-audit ViewModel'inden gelir.

const SEVERITY_STYLE: Record<string, { box: string; chip: string; label: string }> = {
  CRITICAL: {
    box: "border-signal-down/30 bg-signal-down/[0.06]",
    chip: "bg-signal-down/20 text-signal-down",
    label: "KRİTİK",
  },
  WARNING: {
    box: "border-amber-400/25 bg-amber-400/[0.05]",
    chip: "bg-amber-400/20 text-amber-300",
    label: "UYARI",
  },
  INFO: {
    box: "border-white/10 bg-white/[0.02]",
    chip: "bg-white/10 text-white/60",
    label: "BİLGİ",
  },
};

function LessonCard({ lesson }: { lesson: BookAuditLesson }) {
  const s = SEVERITY_STYLE[lesson.severity] ?? SEVERITY_STYLE.INFO;
  return (
    <div className={`rounded-lg border px-3 py-2 ${s.box}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-[13px] font-semibold leading-snug text-white/90">{lesson.title}</div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${s.chip}`}>
          {s.label}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-white/62">{lesson.detail}</p>
      {lesson.evidence.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {lesson.evidence.map((ev, i) => (
            <span
              key={`${lesson.code}-ev-${i}`}
              className="rounded border border-white/8 bg-black/25 px-1.5 py-0.5 font-mono text-[10px] text-white/50"
            >
              {ev}
            </span>
          ))}
        </div>
      ) : null}
      {lesson.suggested_action ? (
        <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-accent-cyan/80">
          <span aria-hidden>→</span>
          <span>{lesson.suggested_action}</span>
        </div>
      ) : null}
    </div>
  );
}

export function BookAuditPanel() {
  const { data, isLoading } = useBookAudit();

  if (isLoading) {
    return (
      <PanelFrame id="book_audit">
        <PanelHeader title="Kitap Denetimi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: BookAuditView | undefined = data;
  const lessons = d?.lessons ?? [];
  const critical = d?.counts?.CRITICAL ?? 0;
  const warning = d?.counts?.WARNING ?? 0;
  const clean = !!d?.clean;

  return (
    <PanelFrame id="book_audit">
      <PanelHeader
        title="Kitap Denetimi"
        subtitle="Açık kitabın yapısal mantık kontrolü"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              clean
                ? "bg-signal-up/20 text-signal-up"
                : critical > 0
                  ? "bg-signal-down/20 text-signal-down"
                  : "bg-amber-400/20 text-amber-300"
            }`}
          >
            {clean ? "TEMİZ" : `${critical} kritik · ${warning} uyarı`}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Açık pozisyonlardaki mantık hatalarını <strong className="text-white/75">kapanış beklemeden</strong> yakalar:
        aynı varlıkta zıt yön, tek varlıkta aşırı yoğunlaşma, aynı sinyalin farklı zaman dilimlerine kopyalanması
        ve tek-yön kitap riski.
      </p>

      {clean ? (
        <div className="rounded-lg border border-signal-up/25 bg-signal-up/5 px-3 py-3 text-[12px] text-signal-up/90">
          Kitap yapısal olarak temiz — belirgin mantık hatası yok.
        </div>
      ) : (
        <div className="space-y-1.5">
          {lessons.map((lesson, i) => (
            <LessonCard key={`${lesson.code}-${i}`} lesson={lesson} />
          ))}
        </div>
      )}

      {d ? (
        <div className="mt-2 text-right text-[10px] uppercase tracking-widest text-white/30">
          {d.open_positions} açık · kitap ${Math.round(d.book_total_usd).toLocaleString()}
        </div>
      ) : null}
    </PanelFrame>
  );
}
