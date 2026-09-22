import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
