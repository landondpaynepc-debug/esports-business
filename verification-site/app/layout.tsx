import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Verify • Royal Services",
  description: "Verify your Royal Services membership using Discord’s official sign-in.",
  robots: {index:false, follow:false},
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
