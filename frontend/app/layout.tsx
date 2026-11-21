import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "AegisLedger — Risk Command Center" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body className="font-mono antialiased min-h-screen">{children}</body></html>);
}
