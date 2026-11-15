import "leaflet/dist/leaflet.css";
import "./globals.css";
import type { ReactNode } from "react";
import { DEFAULTS, PRELOAD_SCRIPT } from "@/lib/settings";

export const metadata = {
  title: "Parallax",
  description: "Does parking-lot usage predict lease renewals? Houston and LA, 2018-2026.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme={DEFAULTS.theme === "light" ? "light" : "dark"} data-text={DEFAULTS.text} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PRELOAD_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:ital,wght@0,400;0,500;0,600;1,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
