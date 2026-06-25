import type { Metadata, Viewport } from "next";

import { GlobalChrome } from "@/components/shell/GlobalChrome";
import { I18nProvider } from "@/providers/I18nProvider";
import { QueryProvider } from "@/providers/QueryProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Clean E-yAy",
  description: "Trading decision-support — paper trading + calibrated heuristic learning",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-screen antialiased">
        <ThemeProvider>
          <I18nProvider>
            <QueryProvider>
              {children}
              <GlobalChrome />
            </QueryProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
