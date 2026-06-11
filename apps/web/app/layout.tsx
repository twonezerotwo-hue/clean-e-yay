import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clean E-yAy",
  description: "Trading decision-support — paper trading + calibrated heuristic learning",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
