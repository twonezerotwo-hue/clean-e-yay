export function EvidenceList({ items }: { items: string[] | undefined }) {
  if (!items?.length) {
    return <div className="text-xs text-white/40 italic">kanıt yok</div>;
  }
  return (
    <ul className="text-xs space-y-1">
      {items.map((s, i) => (
        <li key={i} className="text-white/70 flex gap-2">
          <span className="text-accent-cyan">›</span>
          <span>{s}</span>
        </li>
      ))}
    </ul>
  );
}
