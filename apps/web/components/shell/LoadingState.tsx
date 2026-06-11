export function LoadingState({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center min-h-[6rem] text-sm text-white/40">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent-cyan animate-pulse mr-2" />
      {label}
    </div>
  );
}
