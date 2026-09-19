import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell, AuthProvider } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aegis Eval",
  description:
    "Test AI for the mission, not the benchmark. Evaluate AI systems against the missions, users, environments, risks and adversaries they will actually encounter.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
