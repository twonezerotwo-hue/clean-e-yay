export function EmptyState({ message = "Veri yok." }: { message?: string }) {
  return (
    <div className="flex items-center justify-center min-h-[6rem] text-sm text-white/40 italic">
      {message}
    </div>
  );
}
