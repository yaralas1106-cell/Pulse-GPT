import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TOMI Music Agent",
  description: "AI Music Creation with PulseFormer",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className="h-full">
      <body className="h-full flex flex-col antialiased">{children}</body>
    </html>
  );
}
