import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-3">
      <h1 className="text-xl font-medium">Sayfa bulunamadı.</h1>
      <Link href="/" className="text-accent-cyan hover:underline">
        Panoya dön
      </Link>
    </main>
  );
}
