import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Central Governance — dbt Standards Configurator",
  description: "Configure dbt governance standards and export .dbt-governance.yml, REVIEW.md, and CLAUDE.md."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
