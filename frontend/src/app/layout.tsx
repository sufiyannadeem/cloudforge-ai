import type { Metadata } from "next";

import "./globals.css";
import { ViewerSession } from "@/components/layout/ViewerSession";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

export const metadata: Metadata = {
  title: "CloudForge AI",
  description:
    "Cloud-native platform engineering and AI-Ops console",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <ViewerSession>{children}</ViewerSession>
        </ThemeProvider>
      </body>
    </html>
  );
}
