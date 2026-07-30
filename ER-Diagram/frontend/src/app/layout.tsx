import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SessionProvider } from "next-auth/react";
import AuthGate from "@/components/auth-gate";
import UnifiedNav from "@/components/unified-nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DataLake Orchestrator",
  description: "Connect, visualize, and optimize your data infrastructure",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SessionProvider>
          <AuthGate>
            <UnifiedNav />
            <div className="unified-content">{children}</div>
          </AuthGate>
        </SessionProvider>
      </body>
    </html>
  );
}
