import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import type { ReactNode } from "react";

import { AppShell, AuthProvider } from "@/components/shell";
import "./globals.css";

/*
 * Three faces, each with one job.
 *
 * Geist carries the interface. Geist Mono carries anything a reader might
 * compare character by character -- hashes, identifiers, scenario keys. The
 * serif appears only at display size, where a single line of it gives the
 * page a voice that a grotesque at 30px cannot.
 */
const sans = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const serif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Aegis Eval",
  description:
    "Test AI for the mission, not the benchmark. Evaluate AI systems against the missions, users, environments, risks and adversaries they will actually encounter.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable} ${serif.variable}`}
    >
      <head>
        {/* Applied before paint so a dark-mode reader never sees a white flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('aegis.theme');var d=s==='dark'||(s===null&&matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body className="font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
